web_search_prompt = """
5. Request web searches when you need current information.

**CRITICAL**: To request a web search, you MUST use this EXACT format:

```websearch
your search query here
```

Note: There must be THREE backticks, the word "websearch", a newline, your query, another newline, then THREE closing backticks.

**CORRECT format:**
```websearch
Python command line UI libraries 2025
```

**WRONG formats (don't use these):**
- Just text: "Python command line UI libraries"
- Code block: ```python\nPython libraries```
- Single backticks: `websearch query`

**When to use web search:**
- Latest versions or recent releases
- Current best practices or new APIs
- Recent developments or changes
- Up-to-date documentation
- Any info that may have changed since January 2025

**Complete example conversation:**

User: "What are the best Python CLI libraries?"

You should respond:
```websearch
best Python command line interface libraries 2025
```

Then aider will search and add results to the conversation. The search results will appear, and you can then answer based on those results.

**Important:**
- Use the search BEFORE trying to answer questions about current information
- The search will be executed automatically - don't explain what you're searching for
- Keep queries specific and include the year "2025" for latest information
"""  # noqa

web_search_reminder = """
Remember: You can request web searches for current information using:
```websearch
your search query
```

Use this when you need up-to-date information that may have changed since your training data.
"""  # noqa

scrape_url_prompt = """
6. Request URL scraping when you need detailed content from specific web pages.

**CRITICAL**: After receiving web search results, you MUST scrape the most relevant URLs to get full content before answering.

**MANDATORY WORKFLOW:**
1. Receive search results with URLs
2. Immediately request to scrape 1-3 most relevant URLs using ```scrapeurl blocks
3. Wait for full page content
4. Then provide comprehensive answer based on scraped content

**To request a URL scrape, use this EXACT format:**

```scrapeurl
https://example.com/page
```

Note: There must be THREE backticks, the word "scrapeurl", a newline, your URL, another newline, then THREE closing backticks.

**CORRECT format:**
```scrapeurl
https://developer.apple.com/design/human-interface-guidelines/
```

**WRONG formats (don't use these):**
- Just text: "https://example.com"
- Explaining what you'll do: "I will scrape..."
- Code block: ```python\\nhttps://example.com```
- Single backticks: `scrapeurl url`

**When to use URL scraping:**
- **ALWAYS after getting search results** - search snippets are too brief
- You need to read full documentation, articles, or blog posts
- You want detailed, accurate information from the source
- You want to verify information from a specific source

**Complete example conversation:**

User: "What is Apple's design philosophy?"
AI outputs: ```websearch\nApple design philosophy 2025\n```
Aider shows search results with 5 URLs
AI MUST respond with:
```scrapeurl
https://developer.apple.com/design/human-interface-guidelines/
```
```scrapeurl
https://www.apple.com/newsroom/2025/06/apple-design-announcement/
```

Then aider scrapes the pages and adds content to the conversation. THEN you provide a detailed answer.

**Important:**
- DO NOT try to answer based only on search snippets - they lack detail
- ALWAYS scrape the most relevant URLs first (1-3 URLs)
- You can scrape multiple URLs by using multiple ```scrapeurl blocks
- The scrape will be executed automatically - don't explain what you're doing
- After scraping completes, use the full content to provide a comprehensive answer
"""  # noqa

scrape_url_reminder = """
**CRITICAL REMINDER**: After receiving search results, you MUST scrape relevant URLs before answering!

Use this format to scrape:
```scrapeurl
https://example.com/page
```

DO NOT answer based only on search snippets - always scrape for full details first. Limit to 3 URLs at once.
"""  # noqa
