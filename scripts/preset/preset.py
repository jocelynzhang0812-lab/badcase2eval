description: AI_Platform Chat x35 环境  # Preset 描述
env:  # Sandbox 环境配置，可以不配置，未配置需要保证使用的 tools 都不依赖 sandbox
  template: moonbox:chat  # 使用的 Sandbox Template
  spec: default  # 使用的 Sandbox 规格
  ttl_seconds: 300  # 每次激活 Sandbox 时续多少秒
  init_script: |- # 启动 sandbox 之后调用的初始化命令
    curl -X POST -fs http://127.0.0.1:8080/api/v1/bind_chat \
      -H 'Content-Type: application/json' \
      -d '{
        "chat_id":"{{ .ChatID }}",
        "init_layout": [".store", "output"],
        "upload_path": "upload"
      }' || exit $?
  kaos:  # kaos 配置
    name: ssh
    args:
      cwd: /mnt/AI_Platform  # 工具工作目录
      username: AI_Platform  # 沙箱用户名
exec:  # 工具执行配置
  context:
    llm:
      supports_image_in: true  # 模型是否支持图像输入（视觉模型）
  default_timeout: 60  # 工具执行的默认超时时间
tools:  # 工具定义
  - tool: mshtools.search.web_search_v3:WebSearchV3
    schema:
      name: web_search
      description: |-
        General-purpose web search. Returns top results with relevant snippets.

        ## Query guidelines
        - Keep concise: 1-6 words work best. Most search task can be completed within ONE search query
        - Stay faithful to the YYYY-MM-DD format Current Date from System message.
        - Match user's question language. Only switch language when the content domain requires it (e.g., BBC documentary → English). Do not duplicate queries across languages for coverage. 

        ## Query construction
        Example 1:
        User: "整理2025年11月10日当天发布的涉及医疗卫生热点新闻或舆情的前五项新闻事件"
        Good: ["医疗卫生 热点新闻 舆情 after:2025-11-10 before:2025-11-11"]

        Example 2  Stay faithful to system date (assume system date = 2026-02 here):
        User: "整理一下这个月关于人工智能监管的重要新闻，至少5条"
        Good: ["人工智能监管 新闻 after:2026-02-01"]

        Example 3  Switch language when content domain requires; use operators for precision:
        User: "帮我查询一部BBC的纪录片，主题是money，有3集，第一集是讲述罗伯特清崎的。时间大约是2010年左右。"
        Good: ["BBC纪录片 money 罗伯特清崎 Robert Kiyosaki 2010 3集", "BBC documentary \"Masters of Money\" Keynes Marx Hayek 2012"]

        USE advanced operators when precision matters:
        | Operator | Use case | Example |
        |----------|----------|---------|
        | `site:` | Limit to specific domain | "What does NYT say about sama？" → `site:nytimes.com Sam Altman` |
        | `"exact phrase"` | Must-include terms | "I got 'CUDA out of memory' error" → `"CUDA out of memory" fix |
        | `-` | Exclude terms | "how fast Jaguar can go, i mean the animal, not the car" → `jaguar speed -car` |
        | `intitle:` | Keyword in page title | "Articles with OpenAI-compatible in the title" → `intitle:OpenAI-compatible` |
        | `before:` / `after:` | Date range | "LLM research published before 2024" → `LLM research before:2024-01-01` |
        Note: Advanced operators narrow scope, if results are sparse, fall back to plain query.

      parameters:
        type: object
        properties:
          queries:
            type: array
            items:
              type: string
            description: |-
              Query string(s) sent to the search engine (default 1). Only use multiple (max 2) when the question contains genuinely independent sub-topics.
        required:
        - queries
    init_args:
      base_url: https://internal.company.com
      citation_file_path: "/mnt/AI_Platform/.store/citation.jsonl"
      ab:
        tokenLimit: "10240"
        globalTimeout: "30000"
  - tool: mshtools.search.web_open_url:WebOpenUrl
    schema:
      name: web_open_url
      description: |-
        The `web_open_url` tool opens a specific URL and displays its content, allowing you to access and analyze web pages directly when users provide exact link(s).
      parameters:
        type: object
        properties:
          urls:
            type: array
            items:
              type: string
            description: URLs to fetch.
        required:
        - urls
    init_args:
      base_url: https://internal.company.com
      citation_file_path: "/mnt/AI_Platform/.store/citation.jsonl"
  - tool: mshtools.search.image_search_by_text:ImageSearchByText
    schema:
      name: search_image_by_text
      description: |
        Search images by text query. Returns matching images with titles, descriptions, and URLs.
        ## Query tips
        - Add context: "Marie Curie portrait photo", "Möbius strip 3D illustration"
      parameters:
        type: object
        properties:
          queries:
            type: array
            items:
              type: string
            description: Search directly by queries. All queries will be searched in
              parallel. If you want to search with multiple keywords, put them in a
              single query. All queries results will share the total count.
          total_count:
            type: integer
            description: The number of images to return, default is 10
            default: 10
            minimum: 1
            maximum: 10
          need_download:
            type: boolean
            description: Whether to download the images
            default: true
          download_dir:
            type: string
            description: The directory to save the images, recommend to use absolute
              path
            default: /mnt/AI_Platform/images
        required:
        - queries
    init_args:
      base_url: https://internal.company.com
      lane: ""
  - tool: mshtools.search.image_search_by_image:ImageSearchByImage
    schema:
      name: search_image_by_image
      description: |
        Search similar images by image URL. Returns matching images with titles, descriptions, and URLs.
      parameters:
        type: object
        properties:
          image_url:
            type: string
            description: The URL of the image to search based on, or the local absolute
              file path of the image
          total_count:
            type: integer
            description: The number of images to return, default is 10
            default: 10
            minimum: 1
            maximum: 10
          need_download:
            type: boolean
            description: Whether to download the images
            default: true
          download_dir:
            type: string
            description: The directory to save the images, recommend to use absolute
              path
            default: /tmp/images
        required:
        - image_url
    init_args:
      base_url: https://internal.company.com
      lane: ""
  - tool: mshtools.code.ipython:IPython
    schema:
      name: ipython
      description: |-
        This tool provides an interactive Python execution environment similar to Jupyter Notebook, supporting:
        - Standard Python code execution
        - Data analysis and visualization (default use: matplotlib, one figure per chart, no color specification unless requested)
        - Image processing and editing (based on Pillow and OpenCV)

        Special features:
        - Use ! prefix to execute bash commands, e.g., !ls -la or !pip install numpy
        - Support matplotlib and other libraries for image generation with automatic display
        - When your native vision is insufficient to complete the task(e.g. image is too blurry, upside down), consider use:
          - Support Pillow (PIL) image processing: cropping, scaling, filters, format conversion, etc.
          - Support OpenCV (cv2) image processing: edge detection, color space conversion, morphological operations, etc.

        Return values:
        - Text results: Direct text representation of execution results
        - Image results: Automatically display generated images (such as matplotlib charts, Pillow/OpenCV processed images)
        - Error information: Detailed error messages when execution fails
        - If text result is longer than **10000 characters**, it will be truncated.

        Usage guidelines:
        - Variables and imports persist across executions.
        - For large code blocks, you must split them into multiple executions for better performance.
        - Chinese fonts are already imported; do not modify 'font.family', 'axes.unicode_minus', or 'font.sans-serif' in plt.rcParams.
        - No network access, pip install, requests, urllib, etc. will fail. Use only pre-installed packages
        - Never use print() statement for progress messages ( "Done!", "Processing...")
      parameters:
        type: object
        properties:
          code:
            type: string
            description: Python code to run in the IPython environment. Common data
              science packages are available. Variables and imports persist across executions.
              Use ! prefix for bash commands.
          restart:
            type: boolean
            description: Whether to restart the IPython environment. This will reset all variables and imports.
            default: false
        required:
        - code
    timeout: 128
    init_args:
      exec_timeout: 120
  # X35 Max tools
  - tool: mshtools.data_source:GetDataSourceDesc
    mshtools_server_endpoint: http://agent-reception-mshtools-datasource
    schema:
      name: get_data_source_desc
      description: |-
        The `get_datasource_desc` will return detailed information and API details and parameters about the chosen data source.
         **When to use**
          - If the query pertains to the fields of finance, economy or academia, and the data source is capable of providing these data, this tool should be used.
            - `Financial Stock data`: `yahoo_finance`
            - `Business data`: `tianyancha`
            - `Economic data`: `world_bank_open_data`
            - `Academic data`: `arxiv`, `google_scholar`

        - **Supported data sources**
          - `yahoo_finance`: Get stock information for a given ticker symbol from Yahoo Finance including: Stock Price & Trading Info, Company Information, Financial Metrics, Earnings & Revenue, Margins & Returns, Dividends, Balance Sheet, Ownership, Analyst Coverage, Risk Metrics.
          - `tianyancha`: Tianyancha Enterprise Database: Offers comprehensive query services for enterprise business registration information, operating data, etc. It includes: business information, business risks, listing information, judicial risks, business registration information, value-added services, personnel risks, enterprise development, intellectual property, investment institutions, relationship discovery, group clusters, construction qualifications, private equity funds, personnel-related information, report services, search, etc. There are 17 major categories and 226 interfaces in total.
          - `world_bank_open_data`: A free global development data platform provided by the World Bank. It provides access to all countries in the world and 29,000+ indicators covering economic, social, and environmental metrics including GDP, GNP, population, poverty rates, unemployment, trade, inflation, education, health, and environmental data with time series data from 1960 to present. All national-level data are applicable.
          - `arxiv`: Arxiv is a free preprint server for scientific papers providing comprehensive data and tools for researchers, clinicians, and general users. Supports paper search, download, conversion to markdown, and local storage management with advanced filtering capabilities.
          - `google_scholar`: A freely accessible web search engine that indexes the full text or metadata of scholarly literature across an array of publishing formats and disciplines. It provides comprehensive academic research capabilities including paper search with keyword-based queries returning titles, authors, abstracts, citation counts, publication years and access links. Advanced search supports filtering by author names and publication year ranges. It also offers detailed author profile lookups with academic metrics including h-index, i10-index, total citations, research interests, and major publications. Suitable for academic research, literature reviews, citation analysis, and trend studies.
      parameters:
        type: object
        properties:
          data_source_name:
            description: Name of the data source. Required parameter.
            enum:
            - yahoo_finance
            - arxiv
            - world_bank_open_data
            - tianyancha
            - google_scholar
            type: string
        required:
        - data_source_name
    init_args:
      base_url: http://data-source.mse.msh.work
      timeout_sec: 60
  - tool: mshtools.data_source:GetDataSource
    mshtools_server_endpoint: http://agent-reception-mshtools-datasource
    schema:
      name: get_data_source
      description: |-
        Get a response with data preview and a file from a specific data source API. Use the get_data_source_desc tool first to see available APIs and their parameters.

        **How to use**
        - If the user requests multiple non-consecutive and widely spaced data points, do not obtain the entire time series data. For example: the data for the years 1961, 1992, and 2015. Do not request data from 1961 to 2015.
        - Parameters with the `required` attribute set to `true` must be provided. If the API tool has a parameter named `file_path`, it must be provided.
        - When using `world_bank_open_data` data source with `search indicator` tool, try to search for several items at a time instead of repeatedly calling the function. `world_bank_open_data` tool, when the same country year is used, it should be called once and not separately for each occasion.
        - When using the `arxiv` and `google_scholar` data source, do not use more than 8 words or connect them with 'OR'.

      parameters:
        type: object
        properties:
          api_name:
            description: Name of the API to call (for 'yahoo_finance' data source, an
              example of the available API name is 'get_historical_stock_prices'). Required
              parameter
            type: string
          data_source_name:
            description: Name of the data source. Required parameter.
            enum:
            - yahoo_finance
            - arxiv
            - world_bank_open_data
            - tianyancha
            - google_scholar
            type: string
          params:
            description: Parameters for the API call (e.g., for 'yahoo_finance' data source
              and its 'get_historical_stock_prices' API, the parameters are {'ticker',
              'period', 'interval'}).
            type: object
        required:
        - data_source_name
        - api_name
    init_args:
      base_url: http://data-source.mse.msh.work
      timeout_sec: 60