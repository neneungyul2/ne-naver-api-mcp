"""도구 설명 (Node 버전 `node-v1`의 설명 문구를 그대로 옮겼다: 이모지 + 영어 + 한글)."""

DESCRIPTIONS: dict[str, str] = {
    "search_webkr": (
        "🌐 Search Korean web documents and general content. Comprehensive search across Korean websites and online content. Find articles, information, and documents from various Korean sources. (네이버 웹문서 검색 - 한국 웹사이트 종합 검색)"
    ),
    "search_news": (
        "📰 Search latest Korean news articles from major outlets. Perfect for current events, breaking news, and recent developments. Covers politics, economy, society, and international news. (네이버 뉴스 검색 - 최신 뉴스와 시사 정보)"
    ),
    "search_blog": (
        "✍️ Search personal blogs and reviews for authentic user experiences. Great for product reviews, personal stories, detailed tutorials, and real user opinions. Find genuine Korean perspectives. (네이버 블로그 검색 - 실제 사용자 후기와 개인적 경험)"
    ),
    "search_image": (
        "🖼️ Search for images with Korean context and relevance. Find visual content, infographics, charts, and photos related to your search terms. Great for visual research and content discovery. (네이버 이미지 검색 - 시각적 컨텐츠 발견)"
    ),
    "search_kin": (
        "❓ Search Naver KnowledgeiN for Q&A and community-driven answers. Find solutions to problems, get expert advice, and discover community insights on various topics. (네이버 지식iN 검색 - 질문과 답변, 커뮤니티 지식)"
    ),
    "search_encyc": (
        "📖 Search Naver Encyclopedia for authoritative knowledge and definitions. Best for academic research, getting reliable information, and understanding Korean concepts and terminology. (네이버 지식백과 검색 - 신뢰할 수 있는 정보와 정의)"
    ),
    "search_local": (
        "📍 Search for local businesses, restaurants, and places in Korea. Find location information, reviews, contact details, and business hours for Korean establishments. (네이버 지역 검색 - 지역 업체와 장소 정보)"
    ),
    "search_cafearticle": (
        "☕ Search Naver Cafe articles for community discussions and specialized content. Find niche communities, hobby groups, and specialized discussions on various topics. (네이버 카페글 검색 - 커뮤니티 토론과 전문 정보)"
    ),
    "datalab_search": (
        "📊 Analyze search keyword trends over time using Naver DataLab. Track popularity changes, seasonal patterns, and compare multiple keywords. Perfect for market research and trend analysis. (네이버 데이터랩 검색어 트렌드 분석)"
    ),
    "datalab_shopping_category": (
        "🛍️ STEP 2: Analyze shopping category trends over time. Use find_category first to get category codes. BUSINESS CASES: Market size analysis, seasonal trend identification, category performance comparison. EXAMPLE: Compare '패션의류' vs '화장품' trends over 6 months. (네이버 쇼핑 카테고리별 트렌드 분석 - 먼저 find_category 도구로 카테고리 코드를 찾으세요)"
    ),
    "datalab_shopping_by_device": (
        "📱 Analyze shopping trends by device (PC vs Mobile). Use find_category first. BUSINESS CASES: Mobile commerce strategy, responsive design priority, device-specific campaigns. EXAMPLE: 'PC 사용자가 더 많이 구매하는 카테고리는?' (기기별 쇼핑 트렌드 분석 - 먼저 find_category 도구로 카테고리 코드를 찾으세요)"
    ),
    "datalab_shopping_by_gender": (
        "👥 Analyze shopping trends by gender (Male vs Female). Use find_category first. BUSINESS CASES: Gender-targeted marketing, product positioning, demographic analysis. EXAMPLE: '화장품 쇼핑에서 남녀 비율은?' (성별 쇼핑 트렌드 분석 - 먼저 find_category 도구로 카테고리 코드를 찾으세요)"
    ),
    "datalab_shopping_by_age": (
        "👶👦👨👴 Analyze shopping trends by age groups (10s, 20s, 30s, 40s, 50s, 60s+). Use find_category first. BUSINESS CASES: Age-targeted products, generational preferences, lifecycle marketing. EXAMPLE: '개발 도구는 어느 연령대가 많이 구매하나?' (연령별 쇼핑 트렌드 - 먼저 find_category 도구로 카테고리 코드를 찾으세요)"
    ),
    "datalab_shopping_keywords": (
        "🔍 Compare specific keywords within a shopping category. Use find_category first. BUSINESS CASES: Product keyword optimization, competitor analysis, search trend identification. EXAMPLE: Within '패션' category, compare '원피스' vs '자켓' vs '드레스' trends. (카테고리 내 키워드 비교 - 먼저 find_category 도구로 카테고리 코드를 찾으세요)"
    ),
    "datalab_shopping_keyword_by_device": (
        "📱🔍 Analyze keyword performance by device within shopping categories. Use find_category first to get category codes. Perfect for understanding mobile vs desktop shopping behavior for specific products. (쇼핑 키워드 기기별 트렌드 - 먼저 find_category 도구로 카테고리 코드를 찾으세요)"
    ),
    "datalab_shopping_keyword_by_gender": (
        "👥🔍 Analyze keyword performance by gender within shopping categories. Use find_category first to get category codes. Essential for gender-targeted marketing and product positioning strategies. (쇼핑 키워드 성별 트렌드 - 먼저 find_category 도구로 카테고리 코드를 찾으세요)"
    ),
    "datalab_shopping_keyword_by_age": (
        "👶👦👨👴🔍 Analyze keyword performance by age groups within shopping categories. Use find_category first to get category codes. Perfect for age-targeted marketing and understanding generational shopping preferences. (쇼핑 키워드 연령별 트렌드 - 먼저 find_category 도구로 카테고리 코드를 찾으세요)"
    ),
    "find_category": (
        "🚀 STEP 1: Find shopping categories with Korean search terms. Search in KOREAN (패션, 화장품, 가전제품, etc.) to find category codes needed for datalab tools. Smart fuzzy matching finds similar categories even with partial matches. (카테고리 검색: 한국어로 검색하여 데이터랩 분석에 필요한 카테고리 코드를 찾아주는 필수 도구)"
    ),
    "brand_compare_trend": (
        "📈 Compare relative search/shopping-click trends of several book brands on one common scale (anchor keyword rescaling across batches). Values are relative indexes, not counts. Supports dryRun, call budget and xlsx/csv export. (도서 브랜드 여러 개의 검색어 트렌드 또는 쇼핑 클릭 추이를 기준 브랜드로 환산해 한 척도로 비교. 값은 상대 지수)"
    ),
    "brand_mentions": (
        "📝 Collect blog/cafe/web posts that mention book brands, count them per month (approximate sample), and list co-mentioned candidate terms with examples. Candidate terms are not verified brands — judge them yourself. Supports dryRun, call budget and xlsx/csv export. (도서 브랜드를 언급한 블로그/카페/웹 글을 수집해 월별 집계와 동시 언급 후보 단어를 제공)"
    ),
    "searchad_keyword_volume": (
        "🔎 Look up the monthly (most recent month) PC/mobile search counts of keywords from the NAVER Search Ad keyword tool, optionally with related keywords sorted by volume. Counts under 10 come back as null with lowVolume=true. Spaces are ignored. Requires NAVER_SEARCHAD_* keys. (네이버 검색광고 키워드도구로 키워드의 최근 한 달 PC/모바일 검색수와 연관 키워드를 조회. 10 미만은 null)"
    ),
    "estimate_search_volume": (
        "🧮 Estimate absolute monthly search volume per book brand by scaling NAVER DataLab daily relative indexes to the Search Ad monthly count (calibration on the last 28 days, then summed per month). Approximate: the two sources define counts differently, so read the calibration factors and warnings. Supports dryRun, call budget and xlsx/csv export. Requires NAVER_SEARCHAD_* keys. (데이터랩 상대 지수를 검색광고 월 검색수에 맞춰 월별 절대 검색량으로 역산. 대략적인 추정치)"
    ),
}
