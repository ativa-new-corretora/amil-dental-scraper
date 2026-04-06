from selenium.webdriver.chrome.options import Options


def build_chrome_options(
    user_agent: str | None = None,
    proxy: str | None = None,
) -> Options:
    """
    Cria Options para o Chrome com configs padrão, user-agent correto e (opcionalmente) proxy.
    """
    options = Options()
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=pt-BR")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")

    if user_agent:
        # sem aspas extras pra não bugar
        options.add_argument(f"--user-agent={user_agent}")

    # PROXY HTTP(S) (ex: http://usuario:senha@host:porta)
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")

    prefs = {
        "profile.default_content_setting_values": {
            "notifications": 2,
            "geolocation": 2,
        },
        "profile.managed_default_content_settings": {
            "images": 1,
        },
    }
    options.add_experimental_option("prefs", prefs)
    return options


def apply_stealth(driver) -> None:
    """
    Aplica alguns scripts via CDP para esconder sinais de automação.
    """
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """,
            },
        )
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                window.navigator.chrome = { runtime: {} };
            """,
            },
        )
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """,
            },
        )
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['pt-BR', 'pt', 'en-US', 'en']
                });
            """,
            },
        )
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """,
            },
        )
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32'
                });
            """,
            },
        )
    except Exception as e:
        print(f"⚠️ Aviso: técnicas anti-detecção não puderam ser aplicadas: {e}")