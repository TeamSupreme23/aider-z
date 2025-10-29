#!/usr/bin/env python

import base64
import hashlib
import json
import locale
import math
import mimetypes
import os
import platform
import re
import sys
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime

# Optional dependency: used to convert locale codes (eg ``en_US``)
# into human-readable language names (eg ``English``).
try:
    from babel import Locale  # type: ignore
except ImportError:  # Babel not installed – we will fall back to a small mapping
    Locale = None
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import List

from rich.console import Console

from aider import __version__, models, prompts, urls, utils
from aider.analytics import Analytics
from aider.commands import Commands
from aider.exceptions import LiteLLMExceptions
from aider.history import ChatSummary
from aider.io import ConfirmGroup, InputOutput
from aider.linter import Linter
from aider.llm import litellm
from aider.models import RETRY_TIMEOUT
from aider.reasoning_tags import (
    REASONING_TAG,
    format_reasoning_content,
    remove_reasoning_content,
    replace_reasoning_tags,
)
from aider.repo import ANY_GIT_ERROR, GitRepo
from aider.repomap import RepoMap
from aider.run_cmd import run_cmd
from aider.utils import format_content, format_messages, format_tokens, is_image_file
from aider.waiting import WaitingSpinner

from ..dump import dump  # noqa: F401
from .chat_chunks import ChatChunks


class UnknownEditFormat(ValueError):
    def __init__(self, edit_format, valid_formats):
        self.edit_format = edit_format
        self.valid_formats = valid_formats
        super().__init__(
            f"Unknown edit format {edit_format}. Valid formats are: {', '.join(valid_formats)}"
        )


class MissingAPIKeyError(ValueError):
    pass


class FinishReasonLength(Exception):
    pass


def wrap_fence(name):
    return f"<{name}>", f"</{name}>"


all_fences = [
    ("`" * 3, "`" * 3),
    ("`" * 4, "`" * 4),  # LLMs ignore and revert to triple-backtick, causing #2879
    wrap_fence("source"),
    wrap_fence("code"),
    wrap_fence("pre"),
    wrap_fence("codeblock"),
    wrap_fence("sourcecode"),
]


class Coder:
    abs_fnames = None
    abs_read_only_fnames = None
    repo = None
    last_aider_commit_hash = None
    aider_edited_files = None
    last_asked_for_commit_time = 0
    repo_map = None
    functions = None
    num_exhausted_context_windows = 0
    num_malformed_responses = 0
    last_keyboard_interrupt = None
    num_reflections = 0
    max_reflections = float('inf')  # No limit on reflections
    edit_format = None
    yield_stream = False
    temperature = None
    auto_lint = True
    auto_test = False
    test_cmd = None
    lint_outcome = None
    test_outcome = None
    multi_response_content = ""
    partial_response_content = ""
    commit_before_message = []
    message_cost = 0.0
    add_cache_headers = False
    cache_warming_thread = None
    num_cache_warming_pings = 0
    suggest_shell_commands = True
    auto_execute_shell_commands = False
    detect_urls = True
    ignore_mentions = None
    chat_language = None
    commit_language = None
    file_watcher = None

    # MCP (Model Context Protocol) integration
    enable_mcp = False
    mcp_config = None
    mcp_client = None
    mcp_tools = []

    @classmethod
    def create(
        self,
        main_model=None,
        edit_format=None,
        io=None,
        from_coder=None,
        summarize_from_coder=True,
        **kwargs,
    ):
        import aider.coders as coders

        if not main_model:
            if from_coder:
                main_model = from_coder.main_model
            else:
                main_model = models.Model(models.DEFAULT_MODEL_NAME)

        if edit_format == "code":
            edit_format = None
        if edit_format is None:
            if from_coder:
                edit_format = from_coder.edit_format
            else:
                edit_format = main_model.edit_format

        if not io and from_coder:
            io = from_coder.io

        if from_coder:
            use_kwargs = dict(from_coder.original_kwargs)  # copy orig kwargs

            # If the edit format changes, we can't leave old ASSISTANT
            # messages in the chat history. The old edit format will
            # confused the new LLM. It may try and imitate it, disobeying
            # the system prompt.
            done_messages = from_coder.done_messages
            if edit_format != from_coder.edit_format and done_messages and summarize_from_coder:
                try:
                    done_messages = from_coder.summarizer.summarize_all(done_messages)
                except ValueError:
                    # If summarization fails, keep the original messages and warn the user
                    io.tool_warning(
                        "Chat history summarization failed, continuing with full history"
                    )

            # Bring along context from the old Coder
            update = dict(
                fnames=list(from_coder.abs_fnames),
                read_only_fnames=list(from_coder.abs_read_only_fnames),  # Copy read-only files
                done_messages=done_messages,
                cur_messages=from_coder.cur_messages,
                aider_commit_hashes=from_coder.aider_commit_hashes,
                commands=from_coder.commands.clone(),
                total_cost=from_coder.total_cost,
                ignore_mentions=from_coder.ignore_mentions,
                total_tokens_sent=from_coder.total_tokens_sent,
                total_tokens_received=from_coder.total_tokens_received,
                file_watcher=from_coder.file_watcher,
            )
            use_kwargs.update(update)  # override to complete the switch
            use_kwargs.update(kwargs)  # override passed kwargs

            kwargs = use_kwargs
            from_coder.ok_to_warm_cache = False

        for coder in coders.__all__:
            if hasattr(coder, "edit_format") and coder.edit_format == edit_format:
                res = coder(main_model, io, **kwargs)
                res.original_kwargs = dict(kwargs)
                return res

        valid_formats = [
            str(c.edit_format)
            for c in coders.__all__
            if hasattr(c, "edit_format") and c.edit_format is not None
        ]
        raise UnknownEditFormat(edit_format, valid_formats)

    def clone(self, **kwargs):
        new_coder = Coder.create(from_coder=self, **kwargs)
        return new_coder

    def get_announcements(self):
        lines = []
        # Version, model info, git repo, and repo-map are now shown in the startup banner
        # Only keep warnings and special messages here

        main_model = self.main_model

        # Keep large repo warning
        if self.repo:
            num_files = len(self.repo.get_tracked_files())
            if num_files > 1000:
                lines.append(
                    "Warning: For large repos, consider using --subtree-only and .aiderignore"
                )
                lines.append(f"See: {urls.large_repos}")

        # Keep repo-map warning
        if self.repo_map:
            map_tokens = self.repo_map.max_map_tokens
            if map_tokens > 0:
                max_map_tokens = self.main_model.get_repo_map_tokens() * 2
                if map_tokens > max_map_tokens:
                    lines.append(
                        f"Warning: map-tokens > {max_map_tokens} is not recommended. Too much"
                        " irrelevant code can confuse LLMs."
                    )

        # Files
        for fname in self.get_inchat_relative_files():
            lines.append(f"Added {fname} to the chat.")

        for fname in self.abs_read_only_fnames:
            rel_fname = self.get_rel_fname(fname)
            lines.append(f"Added {rel_fname} to the chat (read-only).")

        if self.done_messages:
            lines.append("Restored previous conversation history.")

        if self.io.multiline_mode:
            lines.append("Multiline mode: Enabled. Enter inserts newline, Alt-Enter submits text")

        return lines

    ok_to_warm_cache = False

    def __init__(
        self,
        main_model,
        io,
        repo=None,
        fnames=None,
        add_gitignore_files=False,
        read_only_fnames=None,
        show_diffs=False,
        auto_commits=True,
        dirty_commits=True,
        dry_run=False,
        map_tokens=1024,
        verbose=False,
        stream=True,
        use_git=True,
        cur_messages=None,
        done_messages=None,
        restore_chat_history=False,
        auto_lint=True,
        auto_test=False,
        lint_cmds=None,
        test_cmd=None,
        aider_commit_hashes=None,
        map_mul_no_files=8,
        commands=None,
        summarizer=None,
        total_cost=0.0,
        analytics=None,
        map_refresh="auto",
        cache_prompts=False,
        num_cache_warming_pings=0,
        suggest_shell_commands=True,
        auto_execute_shell_commands=False,
        enable_mcp=False,
        mcp_config=None,
        chat_language=None,
        commit_language=None,
        detect_urls=True,
        ignore_mentions=None,
        total_tokens_sent=0,
        total_tokens_received=0,
        file_watcher=None,
        auto_copy_context=False,
        auto_accept_architect=True,
    ):
        # Fill in a dummy Analytics if needed, but it is never .enable()'d
        self.analytics = analytics if analytics is not None else Analytics()

        self.event = self.analytics.event
        self.chat_language = chat_language
        self.commit_language = commit_language
        self.commit_before_message = []
        self.aider_commit_hashes = set()
        self.rejected_urls = set()
        self.abs_root_path_cache = {}

        self.auto_copy_context = auto_copy_context
        self.auto_accept_architect = auto_accept_architect

        self.ignore_mentions = ignore_mentions
        if not self.ignore_mentions:
            self.ignore_mentions = set()

        self.file_watcher = file_watcher
        if self.file_watcher:
            self.file_watcher.coder = self

        self.suggest_shell_commands = suggest_shell_commands
        self.auto_execute_shell_commands = auto_execute_shell_commands
        self.detect_urls = detect_urls

        # Initialize MCP attributes (will be initialized after self.io is set)
        self.enable_mcp = enable_mcp
        self.mcp_config = mcp_config
        self.mcp_client = None
        self.mcp_tools = []

        self.num_cache_warming_pings = num_cache_warming_pings

        if not fnames:
            fnames = []

        if io is None:
            io = InputOutput()

        if aider_commit_hashes:
            self.aider_commit_hashes = aider_commit_hashes
        else:
            self.aider_commit_hashes = set()

        self.chat_completion_call_hashes = []
        self.chat_completion_response_hashes = []
        self.need_commit_before_edits = set()

        self.total_cost = total_cost
        self.total_tokens_sent = total_tokens_sent
        self.total_tokens_received = total_tokens_received
        self.message_tokens_sent = 0
        self.message_tokens_received = 0

        self.verbose = verbose
        self.abs_fnames = set()
        self.abs_read_only_fnames = set()
        self.add_gitignore_files = add_gitignore_files

        if cur_messages:
            self.cur_messages = cur_messages
        else:
            self.cur_messages = []

        if done_messages:
            self.done_messages = done_messages
        else:
            self.done_messages = []

        self.io = io

        # Initialize MCP (Model Context Protocol) integration now that self.io is available
        if self.enable_mcp:
            try:
                from aider.mcp import MCPClientManager
                self.io.tool_output("Initializing MCP client...")
                self.mcp_client = MCPClientManager(mcp_config)
                self.mcp_client.initialize()
                # Get tools in LiteLLM format for the LLM
                self.mcp_tools = self.mcp_client.get_tools_for_llm()
                tool_count = len(self.mcp_client.list_tools())
                self.io.tool_output(
                    f"MCP initialized: {len(self.mcp_client.list_servers())} servers, "
                    f"{tool_count} tools available"
                )
            except ImportError:
                self.io.tool_error(
                    "MCP dependencies not installed. "
                    "Run: pip install mcp nest-asyncio"
                )
                self.enable_mcp = False
            except Exception as e:
                self.io.tool_error(f"Failed to initialize MCP: {e}")
                self.enable_mcp = False

        self.shell_commands = []

        if not auto_commits:
            dirty_commits = False

        self.auto_commits = auto_commits
        self.dirty_commits = dirty_commits

        self.dry_run = dry_run
        self.pretty = self.io.pretty

        self.main_model = main_model
        # Set the reasoning tag name based on model settings or default
        self.reasoning_tag_name = (
            self.main_model.reasoning_tag if self.main_model.reasoning_tag else REASONING_TAG
        )

        self.stream = stream and main_model.streaming

        if cache_prompts and self.main_model.cache_control:
            self.add_cache_headers = True

        self.show_diffs = show_diffs

        self.commands = commands or Commands(self.io, self)
        self.commands.coder = self

        self.repo = repo
        if use_git and self.repo is None:
            try:
                self.repo = GitRepo(
                    self.io,
                    fnames,
                    None,
                    models=main_model.commit_message_models(),
                )
            except FileNotFoundError:
                pass

        if self.repo:
            self.root = self.repo.root

        for fname in fnames:
            fname = Path(fname)
            if self.repo and self.repo.git_ignored_file(fname) and not self.add_gitignore_files:
                self.io.tool_warning(f"Skipping {fname} that matches gitignore spec.")
                continue

            if self.repo and self.repo.ignored_file(fname):
                self.io.tool_warning(f"Skipping {fname} that matches aiderignore spec.")
                continue

            if not fname.exists():
                if utils.touch_file(fname):
                    self.io.tool_output(f"Creating empty file {fname}")
                else:
                    self.io.tool_warning(f"Can not create {fname}, skipping.")
                    continue

            if not fname.is_file():
                self.io.tool_warning(f"Skipping {fname} that is not a normal file.")
                continue

            fname = str(fname.resolve())

            self.abs_fnames.add(fname)
            self.check_added_files()

        if not self.repo:
            self.root = utils.find_common_root(self.abs_fnames)

        if read_only_fnames:
            self.abs_read_only_fnames = set()
            for fname in read_only_fnames:
                abs_fname = self.abs_root_path(fname)
                if os.path.exists(abs_fname):
                    self.abs_read_only_fnames.add(abs_fname)
                else:
                    self.io.tool_warning(f"Error: Read-only file {fname} does not exist. Skipping.")

        if map_tokens is None:
            use_repo_map = main_model.use_repo_map
            map_tokens = 1024
        else:
            use_repo_map = map_tokens > 0

        max_inp_tokens = self.main_model.info.get("max_input_tokens") or 0

        has_map_prompt = hasattr(self, "gpt_prompts") and self.gpt_prompts.repo_content_prefix

        if use_repo_map and self.repo and has_map_prompt:
            self.repo_map = RepoMap(
                map_tokens,
                self.root,
                self.main_model,
                io,
                self.gpt_prompts.repo_content_prefix,
                self.verbose,
                max_inp_tokens,
                map_mul_no_files=map_mul_no_files,
                refresh=map_refresh,
            )

        self.summarizer = summarizer or ChatSummary(
            [self.main_model.weak_model, self.main_model],
            self.main_model.max_chat_history_tokens,
        )

        self.summarizer_thread = None
        self.summarized_done_messages = []
        self.summarizing_messages = None

        if not self.done_messages and restore_chat_history:
            history_md = self.io.read_text(self.io.chat_history_file)
            if history_md:
                self.done_messages = utils.split_chat_history_markdown(history_md)
                self.summarize_start()

        # Linting and testing
        self.linter = Linter(root=self.root, encoding=io.encoding)
        self.auto_lint = auto_lint
        self.setup_lint_cmds(lint_cmds)
        self.lint_cmds = lint_cmds
        self.auto_test = auto_test
        self.test_cmd = test_cmd

        # validate the functions jsonschema
        if self.functions:
            from jsonschema import Draft7Validator

            for function in self.functions:
                Draft7Validator.check_schema(function)

            if self.verbose:
                self.io.tool_output("JSON Schema:")
                self.io.tool_output(json.dumps(self.functions, indent=4))

    def setup_lint_cmds(self, lint_cmds):
        if not lint_cmds:
            return
        for lang, cmd in lint_cmds.items():
            self.linter.set_linter(lang, cmd)

    def show_announcements(self):
        bold = True
        for line in self.get_announcements():
            self.io.tool_output(line, bold=bold)
            bold = False

    def add_rel_fname(self, rel_fname):
        self.abs_fnames.add(self.abs_root_path(rel_fname))
        self.check_added_files()

    def drop_rel_fname(self, fname):
        abs_fname = self.abs_root_path(fname)
        if abs_fname in self.abs_fnames:
            self.abs_fnames.remove(abs_fname)
            return True

    def abs_root_path(self, path):
        key = path
        if key in self.abs_root_path_cache:
            return self.abs_root_path_cache[key]

        res = Path(self.root) / path
        res = utils.safe_abs_path(res)
        self.abs_root_path_cache[key] = res
        return res

    fences = all_fences
    fence = fences[0]

    def show_pretty(self):
        if not self.pretty:
            return False

        # only show pretty output if fences are the normal triple-backtick
        if self.fence[0][0] != "`":
            return False

        return True

    def _stop_waiting_spinner(self):
        """Stop and clear the waiting spinner and escape listener if running."""
        spinner = getattr(self, "waiting_spinner", None)
        if spinner:
            try:
                spinner.stop()
            finally:
                self.waiting_spinner = None

        # Also stop escape key listener
        escape_listener = getattr(self, "escape_listener", None)
        if escape_listener:
            try:
                escape_listener.stop()
            finally:
                self.escape_listener = None

    def get_abs_fnames_content(self):
        for fname in list(self.abs_fnames):
            content = self.io.read_text(fname)

            if content is None:
                relative_fname = self.get_rel_fname(fname)
                self.io.tool_warning(f"Dropping {relative_fname} from the chat.")
                self.abs_fnames.remove(fname)
            else:
                yield fname, content

    def choose_fence(self):
        all_content = ""
        for _fname, content in self.get_abs_fnames_content():
            all_content += content + "\n"
        for _fname in self.abs_read_only_fnames:
            content = self.io.read_text(_fname)
            if content is not None:
                all_content += content + "\n"

        lines = all_content.splitlines()
        good = False
        for fence_open, fence_close in self.fences:
            if any(line.startswith(fence_open) or line.startswith(fence_close) for line in lines):
                continue
            good = True
            break

        if good:
            self.fence = (fence_open, fence_close)
        else:
            self.fence = self.fences[0]
            self.io.tool_warning(
                "Unable to find a fencing strategy! Falling back to:"
                f" {self.fence[0]}...{self.fence[1]}"
            )

        return

    def get_files_content(self, fnames=None):
        if not fnames:
            fnames = self.abs_fnames

        prompt = ""
        for fname, content in self.get_abs_fnames_content():
            if not is_image_file(fname):
                relative_fname = self.get_rel_fname(fname)
                prompt += "\n"
                prompt += relative_fname
                prompt += f"\n{self.fence[0]}\n"

                prompt += content

                # lines = content.splitlines(keepends=True)
                # lines = [f"{i+1:03}:{line}" for i, line in enumerate(lines)]
                # prompt += "".join(lines)

                prompt += f"{self.fence[1]}\n"

        return prompt

    def get_read_only_files_content(self):
        prompt = ""
        for fname in self.abs_read_only_fnames:
            content = self.io.read_text(fname)
            if content is not None and not is_image_file(fname):
                relative_fname = self.get_rel_fname(fname)
                prompt += "\n"
                prompt += relative_fname
                prompt += f"\n{self.fence[0]}\n"
                prompt += content
                prompt += f"{self.fence[1]}\n"
        return prompt

    def get_cur_message_text(self):
        text = ""
        for msg in self.cur_messages:
            text += msg["content"] + "\n"
        return text

    def get_ident_mentions(self, text):
        # Split the string on any character that is not alphanumeric
        # \W+ matches one or more non-word characters (equivalent to [^a-zA-Z0-9_]+)
        words = set(re.split(r"\W+", text))
        return words

    def get_ident_filename_matches(self, idents):
        all_fnames = defaultdict(set)
        for fname in self.get_all_relative_files():
            # Skip empty paths or just '.'
            if not fname or fname == ".":
                continue

            try:
                # Handle dotfiles properly
                path = Path(fname)
                base = path.stem.lower()  # Use stem instead of with_suffix("").name
                if len(base) >= 5:
                    all_fnames[base].add(fname)
            except ValueError:
                # Skip paths that can't be processed
                continue

        matches = set()
        for ident in idents:
            if len(ident) < 5:
                continue
            matches.update(all_fnames[ident.lower()])

        return matches

    def get_repo_map(self, force_refresh=False):
        if not self.repo_map:
            return

        cur_msg_text = self.get_cur_message_text()
        mentioned_fnames = self.get_file_mentions(cur_msg_text)
        mentioned_idents = self.get_ident_mentions(cur_msg_text)

        mentioned_fnames.update(self.get_ident_filename_matches(mentioned_idents))

        all_abs_files = set(self.get_all_abs_files())
        repo_abs_read_only_fnames = set(self.abs_read_only_fnames) & all_abs_files
        chat_files = set(self.abs_fnames) | repo_abs_read_only_fnames
        other_files = all_abs_files - chat_files

        repo_content = self.repo_map.get_repo_map(
            chat_files,
            other_files,
            mentioned_fnames=mentioned_fnames,
            mentioned_idents=mentioned_idents,
            force_refresh=force_refresh,
        )

        # fall back to global repo map if files in chat are disjoint from rest of repo
        if not repo_content:
            repo_content = self.repo_map.get_repo_map(
                set(),
                all_abs_files,
                mentioned_fnames=mentioned_fnames,
                mentioned_idents=mentioned_idents,
            )

        # fall back to completely unhinted repo
        if not repo_content:
            repo_content = self.repo_map.get_repo_map(
                set(),
                all_abs_files,
            )

        return repo_content

    def get_repo_messages(self):
        repo_messages = []
        repo_content = self.get_repo_map()
        if repo_content:
            repo_messages += [
                dict(role="user", content=repo_content),
                dict(
                    role="assistant",
                    content="Ok, I won't try and edit those files without asking first.",
                ),
            ]
        return repo_messages

    def get_readonly_files_messages(self):
        readonly_messages = []

        # Handle non-image files
        read_only_content = self.get_read_only_files_content()
        if read_only_content:
            readonly_messages += [
                dict(
                    role="user", content=self.gpt_prompts.read_only_files_prefix + read_only_content
                ),
                dict(
                    role="assistant",
                    content="Ok, I will use these files as references.",
                ),
            ]

        # Handle image files
        images_message = self.get_images_message(self.abs_read_only_fnames)
        if images_message is not None:
            readonly_messages += [
                images_message,
                dict(role="assistant", content="Ok, I will use these images as references."),
            ]

        return readonly_messages

    def get_chat_files_messages(self):
        chat_files_messages = []
        if self.abs_fnames:
            files_content = self.gpt_prompts.files_content_prefix
            files_content += self.get_files_content()
            files_reply = self.gpt_prompts.files_content_assistant_reply
        elif self.get_repo_map() and self.gpt_prompts.files_no_full_files_with_repo_map:
            files_content = self.gpt_prompts.files_no_full_files_with_repo_map
            files_reply = self.gpt_prompts.files_no_full_files_with_repo_map_reply
        else:
            files_content = self.gpt_prompts.files_no_full_files
            files_reply = "Ok."

        if files_content:
            chat_files_messages += [
                dict(role="user", content=files_content),
                dict(role="assistant", content=files_reply),
            ]

        images_message = self.get_images_message(self.abs_fnames)
        if images_message is not None:
            chat_files_messages += [
                images_message,
                dict(role="assistant", content="Ok."),
            ]

        return chat_files_messages

    def get_images_message(self, fnames):
        supports_images = self.main_model.info.get("supports_vision")
        supports_pdfs = self.main_model.info.get("supports_pdf_input") or self.main_model.info.get(
            "max_pdf_size_mb"
        )

        # https://github.com/BerriAI/litellm/pull/6928
        supports_pdfs = supports_pdfs or "claude-3-5-sonnet-20241022" in self.main_model.name

        if not (supports_images or supports_pdfs):
            return None

        image_messages = []
        for fname in fnames:
            if not is_image_file(fname):
                continue

            mime_type, _ = mimetypes.guess_type(fname)
            if not mime_type:
                continue

            with open(fname, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            image_url = f"data:{mime_type};base64,{encoded_string}"
            rel_fname = self.get_rel_fname(fname)

            if mime_type.startswith("image/") and supports_images:
                image_messages += [
                    {"type": "text", "text": f"Image file: {rel_fname}"},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                ]
            elif mime_type == "application/pdf" and supports_pdfs:
                image_messages += [
                    {"type": "text", "text": f"PDF file: {rel_fname}"},
                    {"type": "image_url", "image_url": image_url},
                ]

        if not image_messages:
            return None

        return {"role": "user", "content": image_messages}

    def run_stream(self, user_message):
        self.io.user_input(user_message)
        self.init_before_message()
        yield from self.send_message(user_message)

    def init_before_message(self):
        self.aider_edited_files = set()
        self.reflected_message = None
        self.num_reflections = 0
        self.lint_outcome = None
        self.test_outcome = None
        self.shell_commands = []
        self.message_cost = 0

        if self.repo:
            self.commit_before_message.append(self.repo.get_head_commit_sha())

    def run(self, with_message=None, preproc=True):
        try:
            if with_message:
                self.io.user_input(with_message)
                self.run_one(with_message, preproc)
                return self.partial_response_content
            while True:
                try:
                    if not self.io.placeholder:
                        self.copy_context()
                    user_message = self.get_input()
                    self.run_one(user_message, preproc)
                    self.show_undo_hint()
                except KeyboardInterrupt:
                    self.keyboard_interrupt()
        except EOFError:
            return

    def copy_context(self):
        if self.auto_copy_context:
            self.commands.cmd_copy_context()

    def get_input(self):
        inchat_files = self.get_inchat_relative_files()
        read_only_files = [self.get_rel_fname(fname) for fname in self.abs_read_only_fnames]
        all_files = sorted(set(inchat_files + read_only_files))
        edit_format = "" if self.edit_format == self.main_model.edit_format else self.edit_format
        return self.io.get_input(
            self.root,
            all_files,
            self.get_addable_relative_files(),
            self.commands,
            self.abs_read_only_fnames,
            edit_format=edit_format,
        )

    def preproc_user_input(self, inp):
        if not inp:
            return

        if self.commands.is_command(inp):
            return self.commands.run(inp)

        self.check_for_file_mentions(inp)
        inp = self.check_for_urls(inp)

        return inp

    def run_one(self, user_message, preproc):
        self.init_before_message()

        if preproc:
            message = self.preproc_user_input(user_message)
        else:
            message = user_message

        while message:
            self.reflected_message = None
            list(self.send_message(message))

            if not self.reflected_message:
                break

            if self.num_reflections >= self.max_reflections:
                self.io.tool_warning(f"Only {self.max_reflections} reflections allowed, stopping.")
                return

            self.num_reflections += 1
            message = self.reflected_message

    def check_and_open_urls(self, exc, friendly_msg=None):
        """Check exception for URLs, offer to open in a browser, with user-friendly error msgs."""
        text = str(exc)

        if friendly_msg:
            self.io.tool_warning(text)
            self.io.tool_error(f"{friendly_msg}")
        else:
            self.io.tool_error(text)

        # Exclude double quotes from the matched URL characters
        url_pattern = re.compile(r'(https?://[^\s/$.?#].[^\s"]*)')
        urls = list(set(url_pattern.findall(text)))  # Use set to remove duplicates
        for url in urls:
            url = url.rstrip(".',\"}")  # Added } to the characters to strip
            self.io.offer_url(url)
        return urls

    def check_for_urls(self, inp: str) -> List[str]:
        """Check input for URLs and offer to add them to the chat."""
        if not self.detect_urls:
            return inp

        # Exclude double quotes from the matched URL characters
        url_pattern = re.compile(r'(https?://[^\s/$.?#].[^\s"]*[^\s,.])')
        urls = list(set(url_pattern.findall(inp)))  # Use set to remove duplicates
        group = ConfirmGroup(urls)
        for url in urls:
            if url not in self.rejected_urls:
                url = url.rstrip(".',\"")
                if self.io.confirm_ask(
                    "Add URL to the chat?", subject=url, group=group, allow_never=True
                ):
                    inp += "\n\n"
                    inp += self.commands.cmd_web(url, return_content=True)
                else:
                    self.rejected_urls.add(url)

        return inp

    def keyboard_interrupt(self):
        # Ensure cursor is visible on exit
        Console().show_cursor(True)

        # Check if Escape key was pressed
        escape_listener = getattr(self, "escape_listener", None)
        if escape_listener and escape_listener.escape_pressed:
            # Set message to display before next prompt
            self.io.interrupt_message = "Operation Cancelled by ESC key"
            # Reset the flag
            escape_listener.escape_pressed = False
            return

        now = time.time()

        thresh = 2  # seconds
        if self.last_keyboard_interrupt and now - self.last_keyboard_interrupt < thresh:
            import sys
            sys.stdout.write("\r\033[K")  # Clear current line
            sys.stdout.flush()
            self.io.tool_warning("^C KeyboardInterrupt\n")
            self.event("exit", reason="Control-C")
            sys.exit()

        # Set message to display before next prompt
        self.io.interrupt_message = "^C again to exit"

        self.last_keyboard_interrupt = now

    def summarize_start(self):
        if not self.summarizer.too_big(self.done_messages):
            return

        self.summarize_end()

        if self.verbose:
            self.io.tool_output("Starting to summarize chat history.")

        self.summarizer_thread = threading.Thread(target=self.summarize_worker)
        self.summarizer_thread.start()

    def summarize_worker(self):
        self.summarizing_messages = list(self.done_messages)
        try:
            self.summarized_done_messages = self.summarizer.summarize(self.summarizing_messages)
        except ValueError as err:
            self.io.tool_warning(err.args[0])

        if self.verbose:
            self.io.tool_output("Finished summarizing chat history.")

    def summarize_end(self):
        if self.summarizer_thread is None:
            return

        self.summarizer_thread.join()
        self.summarizer_thread = None

        if self.summarizing_messages == self.done_messages:
            self.done_messages = self.summarized_done_messages
        self.summarizing_messages = None
        self.summarized_done_messages = []

    def move_back_cur_messages(self, message):
        self.done_messages += self.cur_messages
        self.summarize_start()

        # TODO check for impact on image messages
        if message:
            self.done_messages += [
                dict(role="user", content=message),
                dict(role="assistant", content="Ok."),
            ]
        self.cur_messages = []

    def normalize_language(self, lang_code):
        """
        Convert a locale code such as ``en_US`` or ``fr`` into a readable
        language name (e.g. ``English`` or ``French``).  If Babel is
        available it is used for reliable conversion; otherwise a small
        built-in fallback map handles common languages.
        """
        if not lang_code:
            return None

        if lang_code.upper() in ("C", "POSIX"):
            return None

        # Probably already a language name
        if (
            len(lang_code) > 3
            and "_" not in lang_code
            and "-" not in lang_code
            and lang_code[0].isupper()
        ):
            return lang_code

        # Preferred: Babel
        if Locale is not None:
            try:
                loc = Locale.parse(lang_code.replace("-", "_"))
                return loc.get_display_name("en").capitalize()
            except Exception:
                pass  # Fall back to manual mapping

        # Simple fallback for common languages
        fallback = {
            "en": "English",
            "fr": "French",
            "es": "Spanish",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "zh": "Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "ru": "Russian",
        }
        primary_lang_code = lang_code.replace("-", "_").split("_")[0].lower()
        return fallback.get(primary_lang_code, lang_code)

    def get_user_language(self):
        """
        Detect the user's language preference and return a human-readable
        language name such as ``English``. Detection order:

        1. ``self.chat_language`` if explicitly set
        2. ``locale.getlocale()``
        3. ``LANG`` / ``LANGUAGE`` / ``LC_ALL`` / ``LC_MESSAGES`` environment variables
        """

        # Explicit override
        if self.chat_language:
            return self.normalize_language(self.chat_language)

        # System locale
        try:
            lang = locale.getlocale()[0]
            if lang:
                lang = self.normalize_language(lang)
            if lang:
                return lang
        except Exception:
            pass

        # Environment variables
        for env_var in ("LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES"):
            lang = os.environ.get(env_var)
            if lang:
                lang = lang.split(".")[0]  # Strip encoding if present
                return self.normalize_language(lang)

        return None

    def get_platform_info(self):
        platform_text = ""
        try:
            platform_text = f"- Platform: {platform.platform()}\n"
        except KeyError:
            # Skip platform info if it can't be retrieved
            platform_text = "- Platform information unavailable\n"

        shell_var = "COMSPEC" if os.name == "nt" else "SHELL"
        shell_val = os.getenv(shell_var)
        platform_text += f"- Shell: {shell_var}={shell_val}\n"

        user_lang = self.get_user_language()
        if user_lang:
            platform_text += f"- Language: {user_lang}\n"

        dt = datetime.now().astimezone().strftime("%Y-%m-%d")
        platform_text += f"- Current date: {dt}\n"

        if self.repo:
            platform_text += "- The user is operating inside a git repository\n"

        if self.lint_cmds:
            if self.auto_lint:
                platform_text += (
                    "- The user's pre-commit runs these lint commands, don't suggest running"
                    " them:\n"
                )
            else:
                platform_text += "- The user prefers these lint commands:\n"
            for lang, cmd in self.lint_cmds.items():
                if lang is None:
                    platform_text += f"  - {cmd}\n"
                else:
                    platform_text += f"  - {lang}: {cmd}\n"

        if self.test_cmd:
            if self.auto_test:
                platform_text += (
                    "- The user's pre-commit runs this test command, don't suggest running them: "
                )
            else:
                platform_text += "- The user prefers this test command: "
            platform_text += self.test_cmd + "\n"

        return platform_text

    def _format_mcp_tool_prompt(self):
        """
        Format MCP tool instructions for the system prompt.

        Returns:
            String with MCP tool usage instructions
        """
        if not self.mcp_tools:
            return ""

        tool_list = []
        for tool in self.mcp_tools:
            func = tool.get('function', {})
            name = func.get('name', 'unknown')
            desc = func.get('description', 'No description')
            tool_list.append(f"  - {name}: {desc}")

        tools_text = "\n".join(tool_list)

        prompt = f"""
# MCP Tools (Model Context Protocol)

You have access to MCP tools for fetching up-to-date documentation and information:

{tools_text}

## How to Use MCP Tools

**IMPORTANT**: To call an MCP tool, you MUST use the function calling mechanism, NOT text output.

When you need to call a tool:
1. Use the actual function calling API (tool_calls in your response)
2. DO NOT output JSON text like {{"name": "tool_name", "arguments": {{...}}}}
3. The tool will execute and return results automatically
4. You will receive the results in a subsequent message

Example of CORRECT usage:
User: "Get React useState documentation"
Assistant: [Uses tool_calls API to request mcp__context7__resolve-library-id - no text output]
System: [Aider executes the tool and returns results]
Assistant: "Based on the documentation, React's useState hook..."

Example of INCORRECT usage:
User: "Get React useState documentation"
Assistant: {{"name": "mcp__context7__resolve-library-id", "arguments": {{"libraryName": "React"}}}}  ← WRONG! Don't output JSON text.

When to use MCP tools:
- When you need current/latest documentation for libraries, frameworks, or APIs
- When version-specific information is requested
- When you're unsure about API syntax or recent changes
- For accurate, up-to-date code examples

The MCP tools provide more current information than your training data. Use them when appropriate by making actual function calls.
"""
        return prompt.strip()

    def fmt_system_prompt(self, prompt):
        final_reminders = []
        if self.main_model.lazy:
            final_reminders.append(self.gpt_prompts.lazy_prompt)
        if self.main_model.overeager:
            final_reminders.append(self.gpt_prompts.overeager_prompt)

        user_lang = self.get_user_language()
        if user_lang:
            final_reminders.append(f"Reply in {user_lang}.\n")

        platform_text = self.get_platform_info()

        if self.suggest_shell_commands:
            shell_cmd_prompt = self.gpt_prompts.shell_cmd_prompt.format(platform=platform_text)
            shell_cmd_reminder = self.gpt_prompts.shell_cmd_reminder.format(platform=platform_text)
            rename_with_shell = self.gpt_prompts.rename_with_shell
        else:
            shell_cmd_prompt = self.gpt_prompts.no_shell_cmd_prompt.format(platform=platform_text)
            shell_cmd_reminder = self.gpt_prompts.no_shell_cmd_reminder.format(
                platform=platform_text
            )
            rename_with_shell = ""

        # Add MCP tool instructions if enabled
        if self.enable_mcp and self.mcp_tools:
            mcp_tool_prompt = self._format_mcp_tool_prompt()
        else:
            mcp_tool_prompt = ""

        # Add web search instructions
        web_search_prompt = self.gpt_prompts.web_search_prompt
        web_search_reminder = self.gpt_prompts.web_search_reminder

        # Add URL scraping instructions
        scrape_url_prompt = self.gpt_prompts.scrape_url_prompt
        scrape_url_reminder = self.gpt_prompts.scrape_url_reminder

        from aider import debug_logger
        debug_logger.debug("=" * 80)
        debug_logger.debug("SYSTEM PROMPT: Web search instructions")
        debug_logger.debug(f"web_search_prompt is empty: {not web_search_prompt}")
        debug_logger.debug(f"web_search_reminder is empty: {not web_search_reminder}")
        if web_search_prompt:
            debug_logger.debug(f"web_search_prompt preview: {web_search_prompt[:200]}")
        if web_search_reminder:
            debug_logger.debug(f"web_search_reminder preview: {web_search_reminder[:200]}")
        debug_logger.debug(f"scrape_url_prompt is empty: {not scrape_url_prompt}")
        debug_logger.debug(f"scrape_url_reminder is empty: {not scrape_url_reminder}")
        if scrape_url_prompt:
            debug_logger.debug(f"scrape_url_prompt preview: {scrape_url_prompt[:200]}")
        if scrape_url_reminder:
            debug_logger.debug(f"scrape_url_reminder preview: {scrape_url_reminder[:200]}")
        debug_logger.debug("=" * 80)

        if user_lang:  # user_lang is the result of self.get_user_language()
            language = user_lang
        else:
            language = "the same language they are using"  # Default if no specific lang detected

        if self.fence[0] == "`" * 4:
            quad_backtick_reminder = (
                "\nIMPORTANT: Use *quadruple* backticks ```` as fences, not triple backticks!\n"
            )
        else:
            quad_backtick_reminder = ""

        final_reminders = "\n\n".join(final_reminders)

        prompt = prompt.format(
            fence=self.fence,
            quad_backtick_reminder=quad_backtick_reminder,
            final_reminders=final_reminders,
            platform=platform_text,
            shell_cmd_prompt=shell_cmd_prompt,
            rename_with_shell=rename_with_shell,
            shell_cmd_reminder=shell_cmd_reminder,
            go_ahead_tip=self.gpt_prompts.go_ahead_tip,
            language=language,
            mcp_tool_prompt=mcp_tool_prompt,
            web_search_prompt=web_search_prompt,
            web_search_reminder=web_search_reminder,
            scrape_url_prompt=scrape_url_prompt,
            scrape_url_reminder=scrape_url_reminder,
        )

        return prompt

    def format_chat_chunks(self):
        self.choose_fence()
        main_sys = self.fmt_system_prompt(self.gpt_prompts.main_system)
        if self.main_model.system_prompt_prefix:
            main_sys = self.main_model.system_prompt_prefix + "\n" + main_sys

        example_messages = []
        if self.main_model.examples_as_sys_msg:
            if self.gpt_prompts.example_messages:
                main_sys += "\n# Example conversations:\n\n"
            for msg in self.gpt_prompts.example_messages:
                role = msg["role"]
                content = self.fmt_system_prompt(msg["content"])
                main_sys += f"## {role.upper()}: {content}\n\n"
            main_sys = main_sys.strip()
        else:
            for msg in self.gpt_prompts.example_messages:
                example_messages.append(
                    dict(
                        role=msg["role"],
                        content=self.fmt_system_prompt(msg["content"]),
                    )
                )
            if self.gpt_prompts.example_messages:
                example_messages += [
                    dict(
                        role="user",
                        content=(
                            "I switched to a new code base. Please don't consider the above files"
                            " or try to edit them any longer."
                        ),
                    ),
                    dict(role="assistant", content="Ok."),
                ]

        if self.gpt_prompts.system_reminder:
            main_sys += "\n" + self.fmt_system_prompt(self.gpt_prompts.system_reminder)

        chunks = ChatChunks()

        if self.main_model.use_system_prompt:
            chunks.system = [
                dict(role="system", content=main_sys),
            ]
        else:
            chunks.system = [
                dict(role="user", content=main_sys),
                dict(role="assistant", content="Ok."),
            ]

        chunks.examples = example_messages

        self.summarize_end()
        chunks.done = self.done_messages

        chunks.repo = self.get_repo_messages()
        chunks.readonly_files = self.get_readonly_files_messages()
        chunks.chat_files = self.get_chat_files_messages()

        if self.gpt_prompts.system_reminder:
            reminder_message = [
                dict(
                    role="system", content=self.fmt_system_prompt(self.gpt_prompts.system_reminder)
                ),
            ]
        else:
            reminder_message = []

        chunks.cur = list(self.cur_messages)
        chunks.reminder = []

        # TODO review impact of token count on image messages
        messages_tokens = self.main_model.token_count(chunks.all_messages())
        reminder_tokens = self.main_model.token_count(reminder_message)
        cur_tokens = self.main_model.token_count(chunks.cur)

        if None not in (messages_tokens, reminder_tokens, cur_tokens):
            total_tokens = messages_tokens + reminder_tokens + cur_tokens
        else:
            # add the reminder anyway
            total_tokens = 0

        if chunks.cur:
            final = chunks.cur[-1]
        else:
            final = None

        max_input_tokens = self.main_model.info.get("max_input_tokens") or 0
        # Add the reminder prompt if we still have room to include it.
        if (
            not max_input_tokens
            or total_tokens < max_input_tokens
            and self.gpt_prompts.system_reminder
        ):
            if self.main_model.reminder == "sys":
                chunks.reminder = reminder_message
            elif self.main_model.reminder == "user" and final and final["role"] == "user":
                # stuff it into the user message
                new_content = (
                    final["content"]
                    + "\n\n"
                    + self.fmt_system_prompt(self.gpt_prompts.system_reminder)
                )
                chunks.cur[-1] = dict(role=final["role"], content=new_content)

        return chunks

    def format_messages(self):
        chunks = self.format_chat_chunks()
        if self.add_cache_headers:
            chunks.add_cache_control_headers()

        return chunks

    def warm_cache(self, chunks):
        if not self.add_cache_headers:
            return
        if not self.num_cache_warming_pings:
            return
        if not self.ok_to_warm_cache:
            return

        delay = 5 * 60 - 5
        delay = float(os.environ.get("AIDER_CACHE_KEEPALIVE_DELAY", delay))
        self.next_cache_warm = time.time() + delay
        self.warming_pings_left = self.num_cache_warming_pings
        self.cache_warming_chunks = chunks

        if self.cache_warming_thread:
            return

        def warm_cache_worker():
            while self.ok_to_warm_cache:
                time.sleep(1)
                if self.warming_pings_left <= 0:
                    continue
                now = time.time()
                if now < self.next_cache_warm:
                    continue

                self.warming_pings_left -= 1
                self.next_cache_warm = time.time() + delay

                kwargs = dict(self.main_model.extra_params) or dict()
                kwargs["max_tokens"] = 1

                try:
                    completion = litellm.completion(
                        model=self.main_model.name,
                        messages=self.cache_warming_chunks.cacheable_messages(),
                        stream=False,
                        **kwargs,
                    )
                except Exception as err:
                    self.io.tool_warning(f"Cache warming error: {str(err)}")
                    continue

                cache_hit_tokens = getattr(
                    completion.usage, "prompt_cache_hit_tokens", 0
                ) or getattr(completion.usage, "cache_read_input_tokens", 0)

                if self.verbose:
                    self.io.tool_output(f"Warmed {format_tokens(cache_hit_tokens)} cached tokens.")

        self.cache_warming_thread = threading.Timer(0, warm_cache_worker)
        self.cache_warming_thread.daemon = True
        self.cache_warming_thread.start()

        return chunks

    def check_tokens(self, messages):
        """Check if the messages will fit within the model's token limits."""
        input_tokens = self.main_model.token_count(messages)
        max_input_tokens = self.main_model.info.get("max_input_tokens") or 0

        if max_input_tokens and input_tokens >= max_input_tokens:
            self.io.tool_error(
                f"Your estimated chat context of {input_tokens:,} tokens exceeds the"
                f" {max_input_tokens:,} token limit for {self.main_model.name}!"
            )
            self.io.tool_output("To reduce the chat context:")
            self.io.tool_output("- Use /drop to remove unneeded files from the chat")
            self.io.tool_output("- Use /clear to clear the chat history")
            self.io.tool_output("- Break your code into smaller files")
            self.io.tool_output(
                "It's probably safe to try and send the request, most providers won't charge if"
                " the context limit is exceeded."
            )

            if not self.io.confirm_ask("Try to proceed anyway?"):
                return False
        return True

    def send_message(self, inp):
        self.event("message_send_starting")

        # Notify IO that LLM processing is starting
        self.io.llm_started()

        self.cur_messages += [
            dict(role="user", content=inp),
        ]

        chunks = self.format_messages()
        messages = chunks.all_messages()
        if not self.check_tokens(messages):
            return
        self.warm_cache(chunks)

        if self.verbose:
            utils.show_messages(messages, functions=self.functions)

        self.multi_response_content = ""
        if self.show_pretty():
            self.waiting_spinner = WaitingSpinner("Waiting for " + self.main_model.name)
            self.waiting_spinner.start()
            # Start listening for Escape key to cancel
            from aider.waiting import EscapeKeyListener
            self.escape_listener = EscapeKeyListener()
            self.escape_listener.start()
            if self.stream:
                self.mdstream = self.io.get_assistant_mdstream()
            else:
                self.mdstream = None
        else:
            self.mdstream = None

        retry_delay = 0.125

        litellm_ex = LiteLLMExceptions()

        self.usage_report = None
        exhausted = False
        interrupted = False
        try:
            while True:
                try:
                    yield from self.send(messages, functions=self.functions)
                    break
                except litellm_ex.exceptions_tuple() as err:
                    ex_info = litellm_ex.get_ex_info(err)

                    if ex_info.name == "ContextWindowExceededError":
                        exhausted = True
                        break

                    should_retry = ex_info.retry
                    if should_retry:
                        retry_delay *= 2
                        if retry_delay > RETRY_TIMEOUT:
                            should_retry = False

                    if not should_retry:
                        self.mdstream = None
                        self.check_and_open_urls(err, ex_info.description)
                        break

                    err_msg = str(err)
                    if ex_info.description:
                        self.io.tool_warning(err_msg)
                        self.io.tool_error(ex_info.description)
                    else:
                        self.io.tool_error(err_msg)

                    self.io.tool_output(f"Retrying in {retry_delay:.1f} seconds...")
                    time.sleep(retry_delay)
                    continue
                except KeyboardInterrupt:
                    interrupted = True
                    break
                except FinishReasonLength:
                    # We hit the output limit!
                    if not self.main_model.info.get("supports_assistant_prefill"):
                        exhausted = True
                        break

                    self.multi_response_content = self.get_multi_response_content_in_progress()

                    if messages[-1]["role"] == "assistant":
                        messages[-1]["content"] = self.multi_response_content
                    else:
                        messages.append(
                            dict(role="assistant", content=self.multi_response_content, prefix=True)
                        )
                except Exception as err:
                    self.mdstream = None
                    lines = traceback.format_exception(type(err), err, err.__traceback__)
                    self.io.tool_warning("".join(lines))
                    self.io.tool_error(str(err))
                    self.event("message_send_exception", exception=str(err))
                    return
        finally:
            if self.mdstream:
                self.live_incremental_response(True)
                self.mdstream = None

            # Ensure any waiting spinner is stopped
            self._stop_waiting_spinner()

            self.partial_response_content = self.get_multi_response_content_in_progress(True)
            self.remove_reasoning_content()
            self.multi_response_content = ""

        ###
        # print()
        # print("=" * 20)
        # dump(self.partial_response_content)

        self.io.tool_output()

        self.show_usage_report()

        self.add_assistant_reply_to_cur_messages()

        if exhausted:
            if self.cur_messages and self.cur_messages[-1]["role"] == "user":
                self.cur_messages += [
                    dict(
                        role="assistant",
                        content="FinishReasonLength exception: you sent too many tokens",
                    ),
                ]

            self.show_exhausted_error()
            self.num_exhausted_context_windows += 1
            return

        if self.partial_response_function_call:
            args = self.parse_partial_args()
            if args:
                content = args.get("explanation") or ""
            else:
                content = ""
        elif self.partial_response_content:
            content = self.partial_response_content
        else:
            content = ""

        if not interrupted:
            add_rel_files_message = self.check_for_file_mentions(content)
            if add_rel_files_message:
                if self.reflected_message:
                    self.reflected_message += "\n\n" + add_rel_files_message
                else:
                    self.reflected_message = add_rel_files_message
                return

            try:
                if self.reply_completed():
                    return
            except KeyboardInterrupt:
                interrupted = True

        if interrupted:
            if self.cur_messages and self.cur_messages[-1]["role"] == "user":
                self.cur_messages[-1]["content"] += "\n^C KeyboardInterrupt"
            else:
                self.cur_messages += [dict(role="user", content="^C KeyboardInterrupt")]
            self.cur_messages += [
                dict(role="assistant", content="I see that you interrupted my previous reply.")
            ]
            return

        edited = self.apply_updates()

        if edited:
            self.aider_edited_files.update(edited)
            saved_message = self.auto_commit(edited)

            if not saved_message and hasattr(self.gpt_prompts, "files_content_gpt_edits_no_repo"):
                saved_message = self.gpt_prompts.files_content_gpt_edits_no_repo

            self.move_back_cur_messages(saved_message)

        if self.reflected_message:
            return

        if edited and self.auto_lint:
            lint_errors = self.lint_edited(edited)
            self.auto_commit(edited, context="Ran the linter")
            self.lint_outcome = not lint_errors
            if lint_errors:
                ok = self.io.confirm_ask("Attempt to fix lint errors?")
                if ok:
                    self.reflected_message = lint_errors
                    return

        shared_output = self.run_shell_commands()
        if shared_output:
            self.cur_messages += [
                dict(role="user", content=shared_output),
                dict(role="assistant", content="Ok"),
            ]

        if edited and self.auto_test:
            test_errors = self.commands.cmd_test(self.test_cmd)
            self.test_outcome = not test_errors
            if test_errors:
                ok = self.io.confirm_ask("Attempt to fix test errors?")
                if ok:
                    self.reflected_message = test_errors
                    return

    def reply_completed(self):
        pass

    def show_exhausted_error(self):
        output_tokens = 0
        if self.partial_response_content:
            output_tokens = self.main_model.token_count(self.partial_response_content)
        max_output_tokens = self.main_model.info.get("max_output_tokens") or 0

        input_tokens = self.main_model.token_count(self.format_messages().all_messages())
        max_input_tokens = self.main_model.info.get("max_input_tokens") or 0

        total_tokens = input_tokens + output_tokens

        fudge = 0.7

        out_err = ""
        if output_tokens >= max_output_tokens * fudge:
            out_err = " -- possibly exceeded output limit!"

        inp_err = ""
        if input_tokens >= max_input_tokens * fudge:
            inp_err = " -- possibly exhausted context window!"

        tot_err = ""
        if total_tokens >= max_input_tokens * fudge:
            tot_err = " -- possibly exhausted context window!"

        res = ["", ""]
        res.append(f"Model {self.main_model.name} has hit a token limit!")
        res.append("Token counts below are approximate.")
        res.append("")
        res.append(f"Input tokens: ~{input_tokens:,} of {max_input_tokens:,}{inp_err}")
        res.append(f"Output tokens: ~{output_tokens:,} of {max_output_tokens:,}{out_err}")
        res.append(f"Total tokens: ~{total_tokens:,} of {max_input_tokens:,}{tot_err}")

        if output_tokens >= max_output_tokens:
            res.append("")
            res.append("To reduce output tokens:")
            res.append("- Ask for smaller changes in each request.")
            res.append("- Break your code into smaller source files.")
            if "diff" not in self.main_model.edit_format:
                res.append("- Use a stronger model that can return diffs.")

        if input_tokens >= max_input_tokens or total_tokens >= max_input_tokens:
            res.append("")
            res.append("To reduce input tokens:")
            res.append("- Use /tokens to see token usage.")
            res.append("- Use /drop to remove unneeded files from the chat session.")
            res.append("- Use /clear to clear the chat history.")
            res.append("- Break your code into smaller source files.")

        res = "".join([line + "\n" for line in res])
        self.io.tool_error(res)
        self.io.offer_url(urls.token_limits)

    def lint_edited(self, fnames):
        res = ""
        for fname in fnames:
            if not fname:
                continue
            errors = self.linter.lint(self.abs_root_path(fname))

            if errors:
                res += "\n"
                res += errors
                res += "\n"

        if res:
            self.io.tool_warning(res)

        return res

    def __del__(self):
        """Cleanup when the Coder object is destroyed."""
        self.ok_to_warm_cache = False

    def add_assistant_reply_to_cur_messages(self):
        if self.partial_response_content:
            self.cur_messages += [dict(role="assistant", content=self.partial_response_content)]
        if self.partial_response_function_call:
            self.cur_messages += [
                dict(
                    role="assistant",
                    content=None,
                    function_call=self.partial_response_function_call,
                )
            ]

    def get_file_mentions(self, content, ignore_current=False):
        words = set(word for word in content.split())

        # drop sentence punctuation from the end
        words = set(word.rstrip(",.!;:?") for word in words)

        # strip away all kinds of quotes
        quotes = "\"'`*_"
        words = set(word.strip(quotes) for word in words)

        if ignore_current:
            addable_rel_fnames = self.get_all_relative_files()
            existing_basenames = {}
        else:
            addable_rel_fnames = self.get_addable_relative_files()

            # Get basenames of files already in chat or read-only
            existing_basenames = {os.path.basename(f) for f in self.get_inchat_relative_files()} | {
                os.path.basename(self.get_rel_fname(f)) for f in self.abs_read_only_fnames
            }

        mentioned_rel_fnames = set()
        fname_to_rel_fnames = {}
        for rel_fname in addable_rel_fnames:
            normalized_rel_fname = rel_fname.replace("\\", "/")
            normalized_words = set(word.replace("\\", "/") for word in words)
            if normalized_rel_fname in normalized_words:
                mentioned_rel_fnames.add(rel_fname)

            fname = os.path.basename(rel_fname)

            # Don't add basenames that could be plain words like "run" or "make"
            if "/" in fname or "\\" in fname or "." in fname or "_" in fname or "-" in fname:
                if fname not in fname_to_rel_fnames:
                    fname_to_rel_fnames[fname] = []
                fname_to_rel_fnames[fname].append(rel_fname)

        for fname, rel_fnames in fname_to_rel_fnames.items():
            # If the basename is already in chat, don't add based on a basename mention
            if fname in existing_basenames:
                continue
            # If the basename mention is unique among addable files and present in the text
            if len(rel_fnames) == 1 and fname in words:
                mentioned_rel_fnames.add(rel_fnames[0])

        return mentioned_rel_fnames

    def get_nonexistent_file_mentions(self, content):
        """Detect file paths mentioned by LLM that don't exist in the project."""
        words = set(word for word in content.split())

        # drop sentence punctuation from the end
        words = set(word.rstrip(",.!;:?") for word in words)

        # strip away all kinds of quotes
        quotes = "\"'`*_"
        words = set(word.strip(quotes) for word in words)

        nonexistent_files = set()

        # Get all existing files in the repo
        existing_files = set(self.get_all_relative_files())

        # Get files already in chat
        inchat_files = set(self.get_inchat_relative_files())

        for word in words:
            # Look for file-like patterns (containing path separators or extensions)
            if ("/" in word or "\\" in word or "." in word) and not word.startswith("."):
                normalized_word = word.replace("\\", "/")
                # Check if it looks like a file but doesn't exist
                if normalized_word not in existing_files and normalized_word not in inchat_files:
                    # Additional check: has a file extension
                    if "." in os.path.basename(normalized_word):
                        nonexistent_files.add(normalized_word)

        return nonexistent_files

    def check_for_file_mentions(self, content):
        mentioned_rel_fnames = self.get_file_mentions(content)

        new_mentions = mentioned_rel_fnames - self.ignore_mentions

        if not new_mentions:
            return

        added_fnames = []
        # Automatically add all mentioned files without confirmation
        for rel_fname in sorted(new_mentions):
            self.add_rel_fname(rel_fname)
            added_fnames.append(rel_fname)
            # Show user feedback in the chat
            self.io.tool_output(f"Auto-added {rel_fname} to the chat")

        # Check for non-existent files mentioned by the LLM
        nonexistent_files = self.get_nonexistent_file_mentions(content)

        # Show warning for non-existent files in terminal
        if nonexistent_files:
            for fname in sorted(nonexistent_files):
                self.io.tool_warning(f"File mentioned but does not exist: {fname}")

        if added_fnames:
            response = prompts.added_files.format(fnames=", ".join(added_fnames))
            if nonexistent_files:
                response += f"\n\nNote: The following files you mentioned do not exist in this project: {', '.join(sorted(nonexistent_files))}"
            return response
        elif nonexistent_files:
            return f"Note: The following files you mentioned do not exist in this project: {', '.join(sorted(nonexistent_files))}"

    def send(self, messages, model=None, functions=None):
        self.got_reasoning_content = False
        self.ended_reasoning_content = False

        if not model:
            model = self.main_model

        self.partial_response_content = ""
        self.partial_response_function_call = dict()
        self.partial_response_tool_calls = []  # Track tool calls during streaming

        self.io.log_llm_history("TO LLM", format_messages(messages))

        completion = None
        try:
            # Pass MCP tools if available
            mcp_tools = self.mcp_tools if self.enable_mcp and self.mcp_tools else None

            from aider.debug_logger import mcp_debug
            mcp_debug(f"send(): About to call model.send_completion")
            mcp_debug(f"  enable_mcp={self.enable_mcp}")
            mcp_debug(f"  mcp_tools is None: {mcp_tools is None}")
            if mcp_tools:
                mcp_debug(f"  mcp_tools count: {len(mcp_tools)}")
                mcp_debug(f"  mcp_tools[0]: {mcp_tools[0] if mcp_tools else 'N/A'}")
            mcp_debug(f"  functions: {functions}")

            hash_object, completion = model.send_completion(
                messages,
                functions,
                self.stream,
                self.temperature,
                mcp_tools=mcp_tools,
            )
            self.chat_completion_call_hashes.append(hash_object.hexdigest())

            mcp_debug(f"send(): Returned from model.send_completion")
            mcp_debug(f"  stream={self.stream}, enable_mcp={self.enable_mcp}")
            mcp_debug(f"  completion type: {type(completion)}")

            if self.stream:
                mcp_debug("send(): Taking streaming path")
                yield from self.show_send_output_stream(completion)
                mcp_debug("send(): Streaming complete, checking for tool calls")

                # First, check for web search requests
                if self.partial_response_content:
                    search_performed = self.detect_and_execute_websearch(self.partial_response_content)
                    if search_performed:
                        # Search results have been added to chat, continue conversation
                        # so LLM can see the results and respond (e.g., choose URLs to scrape)
                        from aider import debug_logger
                        debug_logger.debug("WEBSEARCH: Continuing conversation after search")
                        chunks = self.format_messages()
                        messages = chunks.all_messages()
                        try:
                            yield from self.send(messages, functions=self.functions)
                        except Exception as e:
                            self.io.tool_error(f"Error continuing after web search: {e}")
                        return

                # Second, check for URL scraping requests
                if self.partial_response_content:
                    scrape_performed = self.detect_and_execute_scrapeurl(self.partial_response_content)
                    if scrape_performed:
                        # Scraped content has been added to chat, continue conversation
                        # so LLM can use the content to answer the original question
                        from aider import debug_logger
                        debug_logger.debug("SCRAPEURL: Continuing conversation after scraping")
                        chunks = self.format_messages()
                        messages = chunks.all_messages()
                        try:
                            yield from self.send(messages, functions=self.functions)
                        except Exception as e:
                            self.io.tool_error(f"Error continuing after URL scraping: {e}")
                        return

                # After streaming, check if we collected any tool calls from the API
                tool_calls_to_process = None

                if self.partial_response_tool_calls:
                    mcp_debug(f"send(): Found {len(self.partial_response_tool_calls)} tool calls from streaming API")
                    # Process tool calls after streaming completes
                    from types import SimpleNamespace
                    tool_calls_to_process = []
                    for tc_dict in self.partial_response_tool_calls:
                        if tc_dict.get('id') and tc_dict.get('function', {}).get('name'):
                            tool_call = SimpleNamespace(
                                id=tc_dict['id'],
                                type='function',
                                function=SimpleNamespace(
                                    name=tc_dict['function']['name'],
                                    arguments=tc_dict['function']['arguments']
                                )
                            )
                            tool_calls_to_process.append(tool_call)
                else:
                    # Fallback: Check if LLM output JSON text instead of using tool_calls API
                    mcp_debug("send(): No tool_calls from API, checking for text-based tool calls")
                    if self.partial_response_content:
                        tool_calls_to_process = self.parse_text_tool_calls(self.partial_response_content)
                        if tool_calls_to_process:
                            mcp_debug(f"send(): Found {len(tool_calls_to_process)} text-based tool calls")

                if tool_calls_to_process:
                        mcp_debug(f"send(): Processing {len(tool_calls_to_process)} tool calls")
                        mcp_results = self.handle_mcp_tool_calls(tool_calls_to_process)

                        if mcp_results:
                            mcp_debug("send(): Got MCP results, continuing conversation")
                            # Add assistant message with tool calls to history
                            self.cur_messages.append({
                                "role": "assistant",
                                "content": self.partial_response_content or "",
                                "tool_calls": [
                                    {
                                        "id": tc.id,
                                        "type": "function",
                                        "function": {
                                            "name": tc.function.name,
                                            "arguments": tc.function.arguments,
                                        }
                                    }
                                    for tc in tool_calls_to_process
                                ]
                            })
                            # Add tool results to chat history
                            self.cur_messages.extend(mcp_results)

                            # Continue the conversation with tool results
                            chunks = self.format_messages()
                            messages = chunks.all_messages()

                            try:
                                # Recursively call send to continue conversation
                                yield from self.send(messages, functions=self.functions)
                            except Exception as e:
                                self.io.tool_error(f"Error continuing after MCP tool call: {e}")
                            return
            else:
                mcp_debug("send(): Taking non-streaming path")
                self.show_send_output(completion)

            # Calculate costs for successful responses
            self.calculate_and_show_tokens_and_cost(messages, completion)

        except LiteLLMExceptions().exceptions_tuple() as err:
            ex_info = LiteLLMExceptions().get_ex_info(err)
            if ex_info.name == "ContextWindowExceededError":
                # Still calculate costs for context window errors
                self.calculate_and_show_tokens_and_cost(messages, completion)
            raise
        except KeyboardInterrupt as kbi:
            self.keyboard_interrupt()
            raise kbi
        finally:
            self.io.log_llm_history(
                "LLM RESPONSE",
                format_content("ASSISTANT", self.partial_response_content),
            )

            if self.partial_response_content:
                self.io.ai_output(self.partial_response_content)
            elif self.partial_response_function_call:
                # TODO: push this into subclasses
                args = self.parse_partial_args()
                if args:
                    self.io.ai_output(json.dumps(args, indent=4))

    def detect_and_execute_websearch(self, content):
        """
        Detect websearch requests in LLM output and execute them.

        Returns:
            True if search was performed, False otherwise
        """
        import re
        from aider import debug_logger

        debug_logger.debug("=" * 80)
        debug_logger.debug("WEBSEARCH DETECTION: Starting")
        debug_logger.debug(f"Content length: {len(content)}")
        debug_logger.debug(f"Content preview (first 500 chars): {content[:500]}")

        # Pattern to match ```websearch\nquery\n```
        pattern = r'```websearch\s*\n(.*?)\n```'
        matches = re.findall(pattern, content, re.DOTALL)

        debug_logger.debug(f"WEBSEARCH: Pattern matches found: {len(matches)}")

        if matches:
            debug_logger.debug(f"WEBSEARCH: Matched queries: {matches}")
        else:
            debug_logger.debug("WEBSEARCH: No matches found. Checking for common issues...")
            # Check if there's any triple backtick blocks
            backtick_blocks = re.findall(r'```(\w+)?\s*\n(.*?)\n```', content, re.DOTALL)
            if backtick_blocks:
                debug_logger.debug(f"WEBSEARCH: Found {len(backtick_blocks)} code blocks with languages: {[b[0] for b in backtick_blocks]}")
            else:
                debug_logger.debug("WEBSEARCH: No code blocks found at all")

        if not matches:
            debug_logger.debug("WEBSEARCH DETECTION: Completed (no searches)")
            debug_logger.debug("=" * 80)
            return False

        # Execute each search
        for i, query in enumerate(matches):
            query = query.strip()
            debug_logger.debug(f"WEBSEARCH: Processing query {i+1}/{len(matches)}: '{query}'")

            if not query:
                debug_logger.debug(f"WEBSEARCH: Query {i+1} is empty, skipping")
                continue

            # Execute the search using the command we created
            if hasattr(self, 'commands') and self.commands:
                print(f"\n🔍 Executing web search: {query}\n")  # Force immediate output
                self.io.tool_output(f"🔍 Executing web search: {query}")
                debug_logger.debug(f"WEBSEARCH: Executing search via commands.cmd_search()")
                try:
                    self.commands.cmd_search(query)
                    debug_logger.debug(f"WEBSEARCH: Search completed successfully")
                    print("\n✅ Web search completed\n")  # Confirm completion
                except Exception as e:
                    debug_logger.error(f"WEBSEARCH: Search failed with error: {str(e)}")
                    import traceback
                    debug_logger.error(traceback.format_exc())
                    self.io.tool_error(f"Web search failed: {str(e)}")
            else:
                debug_logger.warning("WEBSEARCH: Commands object not available")
                self.io.tool_warning("Web search requested but commands not available")

        # Remove the websearch blocks from the content to prevent loops
        # Replace with a marker showing search was executed
        cleaned_content = re.sub(pattern, '[Web search executed]', content, flags=re.DOTALL)
        debug_logger.debug(f"WEBSEARCH: Cleaned content length: {len(cleaned_content)}")
        self.partial_response_content = cleaned_content

        # Add the cleaned response to chat history
        self.cur_messages.append({
            "role": "assistant",
            "content": cleaned_content
        })
        debug_logger.debug("WEBSEARCH: Added cleaned response to chat history")

        debug_logger.debug("WEBSEARCH DETECTION: Completed (searches executed)")
        debug_logger.debug("=" * 80)
        return True

    def detect_and_execute_scrapeurl(self, content):
        """
        Detect scrapeurl requests in LLM output and execute them.

        Returns:
            True if scraping was performed, False otherwise
        """
        import re
        from aider import debug_logger

        debug_logger.debug("=" * 80)
        debug_logger.debug("SCRAPEURL DETECTION: Starting")
        debug_logger.debug(f"Content length: {len(content)}")
        debug_logger.debug(f"Content preview (first 500 chars): {content[:500]}")

        # Pattern to match ```scrapeurl\nurl\n```
        pattern = r'```scrapeurl\s*\n(.*?)\n```'
        matches = re.findall(pattern, content, re.DOTALL)

        debug_logger.debug(f"SCRAPEURL: Pattern matches found: {len(matches)}")

        if matches:
            debug_logger.debug(f"SCRAPEURL: Matched URLs: {matches}")
        else:
            debug_logger.debug("SCRAPEURL: No matches found")

        if not matches:
            debug_logger.debug("SCRAPEURL DETECTION: Completed (no scraping)")
            debug_logger.debug("=" * 80)
            return False

        # Limit to 3 URLs at once
        if len(matches) > 3:
            self.io.tool_warning(f"Found {len(matches)} URLs, limiting to first 3")
            matches = matches[:3]

        # Execute each scrape
        for i, url in enumerate(matches):
            url = url.strip()
            debug_logger.debug(f"SCRAPEURL: Processing URL {i+1}/{len(matches)}: '{url}'")

            if not url:
                debug_logger.debug(f"SCRAPEURL: URL {i+1} is empty, skipping")
                continue

            # Validate URL format
            if not url.startswith(('http://', 'https://')):
                debug_logger.warning(f"SCRAPEURL: Invalid URL format: {url}")
                self.io.tool_warning(f"Invalid URL format (must start with http:// or https://): {url}")
                continue

            # Execute the scrape using the command we have
            if hasattr(self, 'commands') and self.commands:
                print(f"\n🌐 Scraping URL: {url}\n")  # Force immediate output
                self.io.tool_output(f"🌐 Scraping URL: {url}")
                debug_logger.debug(f"SCRAPEURL: Executing scrape via commands.cmd_web()")
                try:
                    self.commands.cmd_web(url)
                    debug_logger.debug(f"SCRAPEURL: Scrape completed successfully")
                    print(f"\n✅ URL scraping completed\n")  # Confirm completion
                except Exception as e:
                    debug_logger.error(f"SCRAPEURL: Scrape failed with error: {str(e)}")
                    import traceback
                    debug_logger.error(traceback.format_exc())
                    self.io.tool_error(f"URL scraping failed: {str(e)}")
            else:
                debug_logger.warning("SCRAPEURL: Commands object not available")
                self.io.tool_warning("URL scraping requested but commands not available")

        # Remove the scrapeurl blocks from the content to prevent loops
        # Replace with a marker showing scraping was executed
        cleaned_content = re.sub(pattern, '[URL scraped]', content, flags=re.DOTALL)
        debug_logger.debug(f"SCRAPEURL: Cleaned content length: {len(cleaned_content)}")
        self.partial_response_content = cleaned_content

        # Add the cleaned response to chat history
        self.cur_messages.append({
            "role": "assistant",
            "content": cleaned_content
        })
        debug_logger.debug("SCRAPEURL: Added cleaned response to chat history")

        debug_logger.debug("SCRAPEURL DETECTION: Completed (scraping executed)")
        debug_logger.debug("=" * 80)
        return True

    def parse_text_tool_calls(self, content):
        """
        Parse tool calls from text output (fallback for models that don't support tool_calls API).

        Supports multiple formats:
        1. JSON: {"name": "mcp__tool__name", "arguments": {"key": "value"}}
        2. Function call: mcp__tool__name(key="value", key2="value2")

        Returns:
            List of tool_call objects in the same format as API tool_calls
        """
        import re
        from types import SimpleNamespace

        from aider.debug_logger import mcp_debug

        tool_calls = []

        # Pattern 1: JSON format
        # Matches: {"name": "tool_name", "arguments": {...}}
        json_pattern = r'\{"name":\s*"(mcp__[^"]+)",\s*"arguments":\s*(\{[^}]*\})\}'
        json_matches = re.finditer(json_pattern, content)

        for idx, match in enumerate(json_matches):
            tool_name = match.group(1)
            arguments_str = match.group(2)

            mcp_debug(f"Detected JSON tool call: {tool_name}")
            mcp_debug(f"  Arguments: {arguments_str}")

            tool_call = SimpleNamespace(
                id=f"text_call_{len(tool_calls)}",
                type='function',
                function=SimpleNamespace(
                    name=tool_name,
                    arguments=arguments_str
                )
            )
            tool_calls.append(tool_call)

        # Pattern 2: Function call format
        # Matches: mcp__tool__name(arg1="value1", arg2="value2")
        func_pattern = r'(mcp__\w+__[\w-]+)\(([^)]*)\)'
        func_matches = re.finditer(func_pattern, content)

        for match in func_matches:
            tool_name = match.group(1)
            args_str = match.group(2)

            mcp_debug(f"Detected function-style tool call: {tool_name}")
            mcp_debug(f"  Raw arguments: {args_str}")

            # Parse function-style arguments into JSON
            # Example: libraryName="React", version="18" -> {"libraryName": "React", "version": "18"}
            args_dict = {}
            if args_str.strip():
                # Match key="value" or key='value' patterns
                arg_pattern = r'(\w+)=(["\'])([^"\']*)\2'
                for arg_match in re.finditer(arg_pattern, args_str):
                    key = arg_match.group(1)
                    value = arg_match.group(3)
                    args_dict[key] = value

            arguments_json = json.dumps(args_dict)
            mcp_debug(f"  Parsed arguments: {arguments_json}")

            tool_call = SimpleNamespace(
                id=f"text_call_{len(tool_calls)}",
                type='function',
                function=SimpleNamespace(
                    name=tool_name,
                    arguments=arguments_json
                )
            )
            tool_calls.append(tool_call)

        return tool_calls if tool_calls else None

    def handle_mcp_tool_calls(self, tool_calls):
        """Handle MCP tool calls from LLM response."""
        from aider.debug_logger import mcp_info, mcp_debug, mcp_error

        # Debug: Log that we're handling tool calls
        mcp_info(f"handle_mcp_tool_calls called with {len(tool_calls)} tool calls")

        if not self.enable_mcp or not self.mcp_client:
            mcp_info(f"MCP disabled or no client: enable_mcp={self.enable_mcp}, mcp_client={self.mcp_client}")
            return None

        results = []
        non_mcp_tools = []

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            mcp_debug(f"Processing tool call: {tool_name}")

            # Check if this is an MCP tool (prefixed with mcp__)
            if not tool_name.startswith("mcp__"):
                mcp_debug(f"Tool {tool_name} does not have mcp__ prefix, skipping")
                non_mcp_tools.append(tool_name)
                continue

            try:
                # Parse arguments
                arguments = json.loads(tool_call.function.arguments)
                mcp_debug(f"Parsed arguments for {tool_name}: {arguments}")

                # Display tool call in a nice format
                self.io.tool_output(f"\n{'='*80}")
                self.io.tool_output(f"🔧 MCP Tool Call: {tool_name}")
                self.io.tool_output(f"{'='*80}")
                if arguments:
                    self.io.tool_output(f"Arguments:")
                    for key, value in arguments.items():
                        self.io.tool_output(f"  • {key}: {value}")
                self.io.tool_output("")

                # Show loading spinner for entire MCP tool processing
                spinner = None
                if self.show_pretty():
                    from aider.waiting import WaitingSpinner
                    spinner = WaitingSpinner(f"Processing {tool_name}...")
                    spinner.start()

                try:
                    # Execute tool via MCP client
                    result = self.mcp_client.call_tool(tool_name, arguments)

                    # Format result for display and storage
                    result_text = ""

                    # Extract text from MCP result
                    if hasattr(result, 'content') and isinstance(result.content, list):
                        # MCP result object with content list
                        for item in result.content:
                            if hasattr(item, 'text'):
                                result_text += item.text + "\n"
                    elif isinstance(result, dict):
                        # Dict result
                        if 'content' in result and isinstance(result['content'], list):
                            for item in result['content']:
                                if hasattr(item, 'text'):
                                    result_text += item.text + "\n"
                                elif isinstance(item, dict) and 'text' in item:
                                    result_text += item['text'] + "\n"
                        else:
                            result_text = json.dumps(result, indent=2)
                    else:
                        # Fallback
                        result_text = str(result)

                    # Display formatted result
                    self.io.tool_output(f"✅ Result:")
                    self.io.tool_output(f"{'-'*80}")

                    # Clean up and display the text
                    if result_text.strip():
                        # Truncate very long results
                        lines = result_text.strip().split('\n')
                        max_lines = 50  # Show first 50 lines max

                        if len(lines) > max_lines:
                            # Show first portion
                            for line in lines[:max_lines]:
                                if line.strip():
                                    self.io.tool_output(line)
                            # Show truncation message
                            self.io.tool_output(f"\n... ({len(lines) - max_lines} more lines truncated)")
                            self.io.tool_output(f"Full result available in chat context for LLM")
                        else:
                            # Show all lines
                            for line in lines:
                                if line.strip():
                                    self.io.tool_output(line)
                    else:
                        self.io.tool_output("(No output)")

                    self.io.tool_output(f"{'-'*80}\n")

                    # Add result to chat history
                    results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_name,
                        "content": result_text.strip(),
                    })
                finally:
                    # Stop spinner after all processing is done
                    if spinner:
                        spinner.stop()

            except Exception as e:
                error_msg = f"MCP tool call failed: {e}"
                self.io.tool_error(error_msg)
                results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": tool_name,
                    "content": error_msg,
                })

        # Log if LLM tried to call tools without proper prefix
        if non_mcp_tools and not results:
            self.io.tool_warning(
                f"LLM called tools without mcp__ prefix: {', '.join(non_mcp_tools)}\n"
                f"Available MCP tools: {', '.join(self.mcp_client.list_tools())}"
            )

        return results if results else None

    def show_send_output(self, completion):
        from aider.debug_logger import mcp_debug
        mcp_debug("=== show_send_output CALLED ===")

        # Stop spinner once we have a response
        self._stop_waiting_spinner()

        if self.verbose:
            print(completion)

        if not completion.choices:
            self.io.tool_error(str(completion))
            mcp_debug("show_send_output: No completion.choices, returning")
            return

        show_func_err = None
        show_content_err = None

        # Check for tool calls - could be from streaming (partial_response_tool_calls)
        # or from non-streaming response (completion.choices[0].message.tool_calls)
        from aider.debug_logger import mcp_info, mcp_debug

        mcp_debug("show_send_output: Checking for tool calls")
        mcp_debug(f"  partial_response_tool_calls has {len(self.partial_response_tool_calls)} items")

        tool_calls = None
        try:
            if completion.choices[0].message.tool_calls:
                tool_calls = completion.choices[0].message.tool_calls
                mcp_info(f"Found {len(tool_calls)} tool calls from completion.message.tool_calls")
        except AttributeError as e:
            mcp_debug(f"No tool_calls in completion.message: {e}")
            pass

        # If no tool calls from completion, check if we collected them during streaming
        if not tool_calls and self.partial_response_tool_calls:
            mcp_info(f"Using {len(self.partial_response_tool_calls)} tool calls from streaming")
            # Convert dict format to proper tool_call objects format
            from types import SimpleNamespace
            tool_calls = []
            for tc_dict in self.partial_response_tool_calls:
                if tc_dict.get('id') and tc_dict.get('function', {}).get('name'):
                    tool_call = SimpleNamespace(
                        id=tc_dict['id'],
                        type='function',
                        function=SimpleNamespace(
                            name=tc_dict['function']['name'],
                            arguments=tc_dict['function']['arguments']
                        )
                    )
                    tool_calls.append(tool_call)

        try:
            if tool_calls:
                # Handle MCP tool calls
                mcp_results = self.handle_mcp_tool_calls(tool_calls)

                if mcp_results:
                    # Get content from completion or partial_response_content
                    try:
                        content = completion.choices[0].message.content or ""
                    except AttributeError:
                        content = self.partial_response_content or ""

                    # Add assistant message with tool calls to history
                    self.cur_messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                }
                            }
                            for tc in tool_calls
                        ]
                    })
                    # Add tool results to chat history
                    self.cur_messages.extend(mcp_results)

                    # Continue the conversation with tool results
                    # Send follow-up request with tool results included
                    chunks = self.format_messages()
                    messages = chunks.all_messages()

                    try:
                        # Recursively call send to continue conversation
                        yield from self.send(messages, functions=self.functions)
                    except Exception as e:
                        self.io.tool_error(f"Error continuing after MCP tool call: {e}")
                    return

                # Not an MCP tool call, handle as normal function call
                # Use the first tool_call if available
                if tool_calls and len(tool_calls) > 0:
                    self.partial_response_function_call = tool_calls[0].function
        except AttributeError as func_err:
            show_func_err = func_err

        try:
            reasoning_content = completion.choices[0].message.reasoning_content
        except AttributeError:
            try:
                reasoning_content = completion.choices[0].message.reasoning
            except AttributeError:
                reasoning_content = None

        try:
            self.partial_response_content = completion.choices[0].message.content or ""
        except AttributeError as content_err:
            show_content_err = content_err

        resp_hash = dict(
            function_call=str(self.partial_response_function_call),
            content=self.partial_response_content,
        )
        resp_hash = hashlib.sha1(json.dumps(resp_hash, sort_keys=True).encode())
        self.chat_completion_response_hashes.append(resp_hash.hexdigest())

        if show_func_err and show_content_err:
            self.io.tool_error(show_func_err)
            self.io.tool_error(show_content_err)
            raise Exception("No data found in LLM response!")

        show_resp = self.render_incremental_response(True)

        if reasoning_content:
            formatted_reasoning = format_reasoning_content(
                reasoning_content, self.reasoning_tag_name
            )
            show_resp = formatted_reasoning + show_resp

        show_resp = replace_reasoning_tags(show_resp, self.reasoning_tag_name)

        self.io.assistant_output(show_resp, pretty=self.show_pretty())

        if (
            hasattr(completion.choices[0], "finish_reason")
            and completion.choices[0].finish_reason == "length"
        ):
            raise FinishReasonLength()

    def show_send_output_stream(self, completion):
        from aider.debug_logger import mcp_debug
        mcp_debug("=== show_send_output_stream CALLED ===")

        received_content = False
        chunk_count = 0

        for chunk in completion:
            chunk_count += 1
            if chunk_count <= 5 or chunk_count % 10 == 0:
                mcp_debug(f"Processing chunk {chunk_count}")

            # Detailed inspection of first chunk
            if chunk_count == 1:
                mcp_debug(f"First chunk inspection:")
                mcp_debug(f"  chunk.choices length: {len(chunk.choices) if hasattr(chunk, 'choices') else 'N/A'}")
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta if hasattr(chunk.choices[0], 'delta') else None
                    if delta:
                        mcp_debug(f"  delta has tool_calls: {hasattr(delta, 'tool_calls')}")
                        mcp_debug(f"  delta has function_call: {hasattr(delta, 'function_call')}")
                        mcp_debug(f"  delta has content: {hasattr(delta, 'content')}")
                        if hasattr(delta, 'tool_calls') and delta.tool_calls:
                            mcp_debug(f"  delta.tool_calls: {delta.tool_calls}")

            if len(chunk.choices) == 0:
                mcp_debug(f"Chunk {chunk_count} has no choices, skipping")
                continue

            if (
                hasattr(chunk.choices[0], "finish_reason")
                and chunk.choices[0].finish_reason == "length"
            ):
                raise FinishReasonLength()

            # Handle tool_calls (new format)
            try:
                tool_calls = chunk.choices[0].delta.tool_calls
                if chunk_count <= 3:  # Log first 3 chunks
                    mcp_debug(f"Chunk {chunk_count}: tool_calls value: {tool_calls}, type: {type(tool_calls)}")
                if tool_calls:
                    mcp_debug(f"Chunk {chunk_count}: Found {len(tool_calls)} tool_calls in delta")
                    for tool_call in tool_calls:
                        # Tool calls come in chunks, need to accumulate them
                        index = tool_call.index if hasattr(tool_call, 'index') else 0

                        # Ensure we have enough slots in the list
                        while len(self.partial_response_tool_calls) <= index:
                            self.partial_response_tool_calls.append({
                                'id': '',
                                'type': 'function',
                                'function': {'name': '', 'arguments': ''}
                            })

                        # Accumulate the tool call data
                        if hasattr(tool_call, 'id') and tool_call.id:
                            self.partial_response_tool_calls[index]['id'] = tool_call.id
                        if hasattr(tool_call, 'function') and tool_call.function:
                            if hasattr(tool_call.function, 'name') and tool_call.function.name:
                                self.partial_response_tool_calls[index]['function']['name'] += tool_call.function.name
                            if hasattr(tool_call.function, 'arguments') and tool_call.function.arguments:
                                self.partial_response_tool_calls[index]['function']['arguments'] += tool_call.function.arguments

                        received_content = True
            except AttributeError:
                pass

            try:
                func = chunk.choices[0].delta.function_call
                # dump(func)
                if func:
                    mcp_debug(f"Chunk {chunk_count}: Found function_call in delta (OLD FORMAT): {func}")
                for k, v in func.items():
                    if k in self.partial_response_function_call:
                        self.partial_response_function_call[k] += v
                    else:
                        self.partial_response_function_call[k] = v
                received_content = True
            except AttributeError:
                pass

            text = ""

            try:
                reasoning_content = chunk.choices[0].delta.reasoning_content
            except AttributeError:
                try:
                    reasoning_content = chunk.choices[0].delta.reasoning
                except AttributeError:
                    reasoning_content = None

            if reasoning_content:
                if not self.got_reasoning_content:
                    text += f"<{REASONING_TAG}>\n\n"
                text += reasoning_content
                self.got_reasoning_content = True
                received_content = True

            try:
                content = chunk.choices[0].delta.content
                if content:
                    if self.got_reasoning_content and not self.ended_reasoning_content:
                        text += f"\n\n</{self.reasoning_tag_name}>\n\n"
                        self.ended_reasoning_content = True

                    text += content
                    received_content = True
            except AttributeError:
                pass

            if received_content:
                self._stop_waiting_spinner()
            self.partial_response_content += text

            if self.show_pretty():
                self.live_incremental_response(False)
            elif text:
                # Apply reasoning tag formatting
                text = replace_reasoning_tags(text, self.reasoning_tag_name)
                try:
                    sys.stdout.write(text)
                except UnicodeEncodeError:
                    # Safely encode and decode the text
                    safe_text = text.encode(sys.stdout.encoding, errors="backslashreplace").decode(
                        sys.stdout.encoding
                    )
                    sys.stdout.write(safe_text)
                sys.stdout.flush()
                yield text

        mcp_debug(f"Stream complete: processed {chunk_count} chunks")
        mcp_debug(f"  partial_response_tool_calls has {len(self.partial_response_tool_calls)} items")
        mcp_debug(f"  partial_response_function_call has {len(self.partial_response_function_call)} keys: {list(self.partial_response_function_call.keys())}")
        mcp_debug(f"  partial_response_content length: {len(self.partial_response_content)}")

        if not received_content:
            self.io.tool_warning("Empty response received from LLM. Check your provider account?")

    def live_incremental_response(self, final):
        show_resp = self.render_incremental_response(final)
        # Apply any reasoning tag formatting
        show_resp = replace_reasoning_tags(show_resp, self.reasoning_tag_name)
        self.mdstream.update(show_resp, final=final)

    def render_incremental_response(self, final):
        return self.get_multi_response_content_in_progress()

    def remove_reasoning_content(self):
        """Remove reasoning content from the model's response."""

        self.partial_response_content = remove_reasoning_content(
            self.partial_response_content,
            self.reasoning_tag_name,
        )

    def calculate_and_show_tokens_and_cost(self, messages, completion=None):
        prompt_tokens = 0
        completion_tokens = 0
        cache_hit_tokens = 0
        cache_write_tokens = 0

        if completion and hasattr(completion, "usage") and completion.usage is not None:
            prompt_tokens = completion.usage.prompt_tokens
            completion_tokens = completion.usage.completion_tokens
            cache_hit_tokens = getattr(completion.usage, "prompt_cache_hit_tokens", 0) or getattr(
                completion.usage, "cache_read_input_tokens", 0
            )
            cache_write_tokens = getattr(completion.usage, "cache_creation_input_tokens", 0)

            if hasattr(completion.usage, "cache_read_input_tokens") or hasattr(
                completion.usage, "cache_creation_input_tokens"
            ):
                self.message_tokens_sent += prompt_tokens
                self.message_tokens_sent += cache_write_tokens
            else:
                self.message_tokens_sent += prompt_tokens

        else:
            prompt_tokens = self.main_model.token_count(messages)
            completion_tokens = self.main_model.token_count(self.partial_response_content)
            self.message_tokens_sent += prompt_tokens

        self.message_tokens_received += completion_tokens

        tokens_report = f"Tokens: {format_tokens(self.message_tokens_sent)} sent"

        if cache_write_tokens:
            tokens_report += f", {format_tokens(cache_write_tokens)} cache write"
        if cache_hit_tokens:
            tokens_report += f", {format_tokens(cache_hit_tokens)} cache hit"
        tokens_report += f", {format_tokens(self.message_tokens_received)} received."

        if not self.main_model.info.get("input_cost_per_token"):
            self.usage_report = tokens_report
            return

        try:
            # Try and use litellm's built in cost calculator. Seems to work for non-streaming only?
            cost = litellm.completion_cost(completion_response=completion)
        except Exception:
            cost = 0

        if not cost:
            cost = self.compute_costs_from_tokens(
                prompt_tokens, completion_tokens, cache_write_tokens, cache_hit_tokens
            )

        self.total_cost += cost
        self.message_cost += cost

        def format_cost(value):
            if value == 0:
                return "0.00"
            magnitude = abs(value)
            if magnitude >= 0.01:
                return f"{value:.2f}"
            else:
                return f"{value:.{max(2, 2 - int(math.log10(magnitude)))}f}"

        cost_report = (
            f"Cost: ${format_cost(self.message_cost)} message,"
            f" ${format_cost(self.total_cost)} session."
        )

        if cache_hit_tokens and cache_write_tokens:
            sep = "\n"
        else:
            sep = " "

        self.usage_report = tokens_report + sep + cost_report

    def compute_costs_from_tokens(
        self, prompt_tokens, completion_tokens, cache_write_tokens, cache_hit_tokens
    ):
        cost = 0

        input_cost_per_token = self.main_model.info.get("input_cost_per_token") or 0
        output_cost_per_token = self.main_model.info.get("output_cost_per_token") or 0
        input_cost_per_token_cache_hit = (
            self.main_model.info.get("input_cost_per_token_cache_hit") or 0
        )

        # deepseek
        # prompt_cache_hit_tokens + prompt_cache_miss_tokens
        #    == prompt_tokens == total tokens that were sent
        #
        # Anthropic
        # cache_creation_input_tokens + cache_read_input_tokens + prompt
        #    == total tokens that were

        if input_cost_per_token_cache_hit:
            # must be deepseek
            cost += input_cost_per_token_cache_hit * cache_hit_tokens
            cost += (prompt_tokens - input_cost_per_token_cache_hit) * input_cost_per_token
        else:
            # hard code the anthropic adjustments, no-ops for other models since cache_x_tokens==0
            cost += cache_write_tokens * input_cost_per_token * 1.25
            cost += cache_hit_tokens * input_cost_per_token * 0.10
            cost += prompt_tokens * input_cost_per_token

        cost += completion_tokens * output_cost_per_token
        return cost

    def show_usage_report(self):
        if not self.usage_report:
            return

        self.total_tokens_sent += self.message_tokens_sent
        self.total_tokens_received += self.message_tokens_received

        self.io.tool_output(self.usage_report)

        prompt_tokens = self.message_tokens_sent
        completion_tokens = self.message_tokens_received
        self.event(
            "message_send",
            main_model=self.main_model,
            edit_format=self.edit_format,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost=self.message_cost,
            total_cost=self.total_cost,
        )

        self.message_cost = 0.0
        self.message_tokens_sent = 0
        self.message_tokens_received = 0

    def get_multi_response_content_in_progress(self, final=False):
        cur = self.multi_response_content or ""
        new = self.partial_response_content or ""

        if new.rstrip() != new and not final:
            new = new.rstrip()

        return cur + new

    def get_rel_fname(self, fname):
        try:
            return os.path.relpath(fname, self.root)
        except ValueError:
            return fname

    def get_inchat_relative_files(self):
        files = [self.get_rel_fname(fname) for fname in self.abs_fnames]
        return sorted(set(files))

    def is_file_safe(self, fname):
        try:
            return Path(self.abs_root_path(fname)).is_file()
        except OSError:
            return

    def get_all_relative_files(self):
        if self.repo:
            files = self.repo.get_tracked_files()
        else:
            files = self.get_inchat_relative_files()

        # This is quite slow in large repos
        # files = [fname for fname in files if self.is_file_safe(fname)]

        return sorted(set(files))

    def get_all_abs_files(self):
        files = self.get_all_relative_files()
        files = [self.abs_root_path(path) for path in files]
        return files

    def get_addable_relative_files(self):
        all_files = set(self.get_all_relative_files())
        inchat_files = set(self.get_inchat_relative_files())
        read_only_files = set(self.get_rel_fname(fname) for fname in self.abs_read_only_fnames)
        return all_files - inchat_files - read_only_files

    def check_for_dirty_commit(self, path):
        if not self.repo:
            return
        if not self.dirty_commits:
            return
        if not self.repo.is_dirty(path):
            return

        # We need a committed copy of the file in order to /undo, so skip this
        # fullp = Path(self.abs_root_path(path))
        # if not fullp.stat().st_size:
        #     return

        self.io.tool_output(f"Committing {path} before applying edits.")
        self.need_commit_before_edits.add(path)

    def allowed_to_edit(self, path):
        full_path = self.abs_root_path(path)
        if self.repo:
            need_to_add = not self.repo.path_in_repo(path)
        else:
            need_to_add = False

        if full_path in self.abs_fnames:
            self.check_for_dirty_commit(path)
            return True

        if self.repo and self.repo.git_ignored_file(path):
            self.io.tool_warning(f"Skipping edits to {path} that matches gitignore spec.")
            return

        if not Path(full_path).exists():
            if not self.io.confirm_ask("Create new file?", subject=path):
                self.io.tool_output(f"Skipping edits to {path}")
                return

            if not self.dry_run:
                if not utils.touch_file(full_path):
                    self.io.tool_error(f"Unable to create {path}, skipping edits.")
                    return

                # Seems unlikely that we needed to create the file, but it was
                # actually already part of the repo.
                # But let's only add if we need to, just to be safe.
                if need_to_add:
                    self.repo.repo.git.add(full_path)

            self.abs_fnames.add(full_path)
            self.check_added_files()
            return True

        if not self.io.confirm_ask(
            "Allow edits to file that has not been added to the chat?",
            subject=path,
        ):
            self.io.tool_output(f"Skipping edits to {path}")
            return

        if need_to_add:
            self.repo.repo.git.add(full_path)

        self.abs_fnames.add(full_path)
        self.check_added_files()
        self.check_for_dirty_commit(path)

        return True

    warning_given = False

    def check_added_files(self):
        if self.warning_given:
            return

        warn_number_of_files = 4
        warn_number_of_tokens = 20 * 1024

        num_files = len(self.abs_fnames)
        if num_files < warn_number_of_files:
            return

        tokens = 0
        for fname in self.abs_fnames:
            if is_image_file(fname):
                continue
            content = self.io.read_text(fname)
            tokens += self.main_model.token_count(content)

        if tokens < warn_number_of_tokens:
            return

        self.io.tool_warning("Warning: it's best to only add files that need changes to the chat.")
        self.io.tool_warning(urls.edit_errors)
        self.warning_given = True

    def prepare_to_edit(self, edits):
        res = []
        seen = dict()

        self.need_commit_before_edits = set()

        for edit in edits:
            path = edit[0]
            if path is None:
                res.append(edit)
                continue
            if path == "python":
                dump(edits)
            if path in seen:
                allowed = seen[path]
            else:
                allowed = self.allowed_to_edit(path)
                seen[path] = allowed

            if allowed:
                res.append(edit)

        self.dirty_commit()
        self.need_commit_before_edits = set()

        return res

    def apply_updates(self):
        edited = set()
        try:
            edits = self.get_edits()
            edits = self.apply_edits_dry_run(edits)
            edits = self.prepare_to_edit(edits)
            edited = set(edit[0] for edit in edits)

            self.apply_edits(edits)
        except ValueError as err:
            self.num_malformed_responses += 1

            err = err.args[0]

            self.io.tool_error("The LLM did not conform to the edit format.")
            self.io.tool_output(urls.edit_errors)
            self.io.tool_output()
            self.io.tool_output(str(err))

            self.reflected_message = str(err)
            return edited

        except ANY_GIT_ERROR as err:
            self.io.tool_error(str(err))
            return edited
        except Exception as err:
            self.io.tool_error("Exception while updating files:")
            self.io.tool_error(str(err), strip=False)

            traceback.print_exc()

            self.reflected_message = str(err)
            return edited

        for path in edited:
            if self.dry_run:
                self.io.tool_output(f"Did not apply edit to {path} (--dry-run)")
            else:
                self.io.tool_output(f"Applied edit to {path}")

        return edited

    def parse_partial_args(self):
        # dump(self.partial_response_function_call)

        data = self.partial_response_function_call.get("arguments")
        if not data:
            return

        try:
            return json.loads(data)
        except JSONDecodeError:
            pass

        try:
            return json.loads(data + "]}")
        except JSONDecodeError:
            pass

        try:
            return json.loads(data + "}]}")
        except JSONDecodeError:
            pass

        try:
            return json.loads(data + '"}]}')
        except JSONDecodeError:
            pass

    # commits...

    def get_context_from_history(self, history):
        context = ""
        if history:
            for msg in history:
                context += "\n" + msg["role"].upper() + ": " + msg["content"] + "\n"

        return context

    def auto_commit(self, edited, context=None):
        if not self.repo or not self.auto_commits or self.dry_run:
            return

        if not context:
            context = self.get_context_from_history(self.cur_messages)

        try:
            res = self.repo.commit(fnames=edited, context=context, aider_edits=True, coder=self)
            if res:
                self.show_auto_commit_outcome(res)
                commit_hash, commit_message = res
                return self.gpt_prompts.files_content_gpt_edits.format(
                    hash=commit_hash,
                    message=commit_message,
                )

            return self.gpt_prompts.files_content_gpt_no_edits
        except ANY_GIT_ERROR as err:
            self.io.tool_error(f"Unable to commit: {str(err)}")
            return

    def show_auto_commit_outcome(self, res):
        commit_hash, commit_message = res
        self.last_aider_commit_hash = commit_hash
        self.aider_commit_hashes.add(commit_hash)
        self.last_aider_commit_message = commit_message
        if self.show_diffs:
            self.commands.cmd_diff()

    def show_undo_hint(self):
        if not self.commit_before_message:
            return
        if self.commit_before_message[-1] != self.repo.get_head_commit_sha():
            self.io.tool_output("You can use /undo to undo and discard each aider commit.")

    def dirty_commit(self):
        if not self.need_commit_before_edits:
            return
        if not self.dirty_commits:
            return
        if not self.repo:
            return

        self.repo.commit(fnames=self.need_commit_before_edits, coder=self)

        # files changed, move cur messages back behind the files messages
        # self.move_back_cur_messages(self.gpt_prompts.files_content_local_edits)
        return True

    def get_edits(self, mode="update"):
        return []

    def apply_edits(self, edits):
        return

    def apply_edits_dry_run(self, edits):
        return edits

    def run_shell_commands(self):
        if not self.suggest_shell_commands:
            return ""

        done = set()
        group = ConfirmGroup(set(self.shell_commands))
        accumulated_output = ""
        for command in self.shell_commands:
            if command in done:
                continue
            done.add(command)
            output = self.handle_shell_commands(command, group)
            if output:
                accumulated_output += output + "\n\n"
        return accumulated_output

    def handle_shell_commands(self, commands_str, group):
        commands = commands_str.strip().splitlines()
        command_count = sum(
            1 for cmd in commands if cmd.strip() and not cmd.strip().startswith("#")
        )
        prompt = "Run shell command?" if command_count == 1 else "Run shell commands?"

        # Skip confirmation if auto_execute_shell_commands is enabled
        if not self.auto_execute_shell_commands:
            if not self.io.confirm_ask(
                prompt,
                subject="\n".join(commands),
                explicit_yes_required=True,
                group=group,
                allow_never=True,
            ):
                return
        else:
            # Show what commands will be auto-executed
            self.io.tool_output(f"Auto-executing shell command{'s' if command_count > 1 else ''}:")
            for cmd in commands:
                if cmd.strip() and not cmd.strip().startswith("#"):
                    self.io.tool_output(f"  {cmd}")

        accumulated_output = ""
        for command in commands:
            command = command.strip()
            if not command or command.startswith("#"):
                continue

            self.io.tool_output()
            self.io.tool_output(f"Running {command}")
            # Add the command to input history
            self.io.add_to_input_history(f"/run {command.strip()}")
            exit_status, output = run_cmd(command, error_print=self.io.tool_error, cwd=self.root)
            if output:
                accumulated_output += f"Output from {command}\n{output}\n"

        # Auto-add output to chat if auto_execute_shell_commands is enabled
        if accumulated_output.strip():
            if self.auto_execute_shell_commands or self.io.confirm_ask(
                "Add command output to the chat?", allow_never=True
            ):
                num_lines = len(accumulated_output.strip().splitlines())
                line_plural = "line" if num_lines == 1 else "lines"
                self.io.tool_output(f"Added {num_lines} {line_plural} of output to the chat.")
                return accumulated_output
