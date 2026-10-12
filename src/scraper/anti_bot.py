import os
import random
import re
from pathlib import Path

from selenium.webdriver.chrome.options import Options


def detectar_versao_chrome() -> int | None:
    """
    Descobre a versão principal (major) do Chrome instalado.
    Lê a pasta de instalação (fonte confiável) e, se não achar, o registro —
    o valor do registro pode ficar desatualizado depois de um auto-update.
    Retorna None se não conseguir — o undetected_chromedriver resolve sozinho.
    """
    candidatos = [
        Path(os.getenv("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application",
        Path(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application",
        Path(os.getenv("LOCALAPPDATA", "")) / "Google/Chrome/Application",
    ]
    for pasta in candidatos:
        # A pasta Application tem uma subpasta com o nome da versão (ex.: 155.0.8059.39).
        # Pode haver duas durante um update — vale a maior.
        if pasta.exists():
            versoes = [
                int(sub.name.split(".")[0])
                for sub in pasta.iterdir()
                if sub.is_dir() and re.match(r"^\d+\.\d+\.\d+\.\d+$", sub.name)
            ]
            if versoes:
                return max(versoes)

    try:
        import winreg
        for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(raiz, r"Software\Google\Chrome\BLBeacon") as chave:
                    versao, _ = winreg.QueryValueEx(chave, "version")
                    return int(str(versao).split(".")[0])
            except OSError:
                continue
    except ImportError:
        pass
    return None


def user_agent_para_versao(versao: int | None) -> str | None:
    """UA coerente com o Chrome real — UA de outra versão é um mismatch detectável."""
    if not versao:
        return None
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{versao}.0.0.0 Safari/537.36"
    )


def preparar_driver_proprio(tag: str) -> str | None:
    """
    Copia o chromedriver já patcheado para um arquivo exclusivo deste processo.

    Sem isso o undetected_chromedriver apaga e baixa de novo o mesmo
    undetected_chromedriver.exe a cada navegador aberto: fica lento e dois
    processos em paralelo brigam pelo mesmo arquivo. Retorna o caminho da
    cópia, ou None se ainda não houver um driver baixado (o UC baixa sozinho).
    """
    import shutil
    pasta = Path(os.getenv("APPDATA", "")) / "undetected_chromedriver"
    origem = pasta / "undetected_chromedriver.exe"
    if not origem.exists():
        return None
    destino = pasta / "fixos" / f"chromedriver_{tag}.exe"
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(origem, destino)
    except PermissionError:
        # cópia anterior ainda em uso por um Chrome desta mesma tag — serve
        pass
    return str(destino) if destino.exists() else None


def janela_oculta() -> bool:
    """
    AMIL_JANELA_OCULTA=1 abre o Chrome fora da área visível da tela.
    Continua sendo um Chrome "com janela" (não headless, que é mais fácil de
    detectar), mas não rouba o foco nem atrapalha quem está usando o PC.
    """
    return os.getenv("AMIL_JANELA_OCULTA", "0") == "1"


def build_chrome_options(
    user_agent: str | None = None,
    proxy: str | None = None,
) -> Options:
    options = Options()
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=pt-BR")
    if janela_oculta():
        options.add_argument("--window-position=-32000,-32000")
        # Sem isso o Chrome reduz o ritmo de páginas em janelas que não estão visíveis
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-background-timer-throttling")
    else:
        options.add_argument("--start-maximized")
    options.add_argument("--disable-infobars")
    # Só o último --disable-features vale, por isso tudo numa linha só
    features_off = ["IsolateOrigins", "site-per-process"]
    if janela_oculta():
        # Sem isso o Windows marca a janela fora da tela como ocluída e o Chrome para de pintar
        features_off.append("CalculateNativeWinOcclusion")
    options.add_argument(f"--disable-features={','.join(features_off)}")
    # Remove o flag "Chrome está sendo controlado por software de automação"
    options.add_argument("--disable-blink-features=AutomationControlled")

    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")

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
    Injeta scripts anti-detecção via CDP usando Page.addScriptToEvaluateOnNewDocument.

    CRÍTICO: deve ser chamado ANTES de driver.get() para que os scripts
    sejam injetados em cada novo documento antes que qualquer JS da página rode.
    """
    # Valores de ruído únicos por sessão para variar o canvas fingerprint
    noise_r = random.randint(1, 8)
    noise_g = random.randint(1, 8)
    noise_b = random.randint(1, 8)

    scripts = [
        # 1. Remove o flag navigator.webdriver
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        """,

        # 2. chrome.runtime realista (Chrome sem automação tem esse objeto)
        """
        if (!window.chrome) { window.chrome = {}; }
        if (!window.chrome.runtime) {
            window.chrome.runtime = {
                id: undefined,
                connect: function() {},
                sendMessage: function() {},
                onMessage:  { addListener: function() {}, removeListener: function() {} },
                onConnect:  { addListener: function() {}, removeListener: function() {} }
            };
        }
        """,

        # 3. navigator.plugins com os 5 plugins PDF padrão do Chrome (não [1,2,3,4,5])
        """
        (function() {
            const makeMime = (type, suffixes, desc) => ({ type, suffixes, description: desc });
            const makePlugin = (name, desc, filename, mimes) => {
                const p = { name, description: desc, filename, length: mimes.length };
                mimes.forEach((m, i) => {
                    const mt = Object.assign({}, m);
                    Object.defineProperty(mt, 'enabledPlugin', { get: () => p });
                    p[i] = mt;
                });
                p.item      = (i) => p[i] || null;
                p.namedItem = (n) => mimes.find(m => m.type === n) || null;
                return p;
            };

            const pdfMimes = [
                makeMime('application/pdf', 'pdf', 'Portable Document Format'),
                makeMime('text/pdf',        'pdf', 'Portable Document Format')
            ];

            const plugins = [
                makePlugin('PDF Viewer',                 'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
                makePlugin('Chrome PDF Viewer',          'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
                makePlugin('Chromium PDF Viewer',        'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
                makePlugin('Microsoft Edge PDF Viewer',  'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
                makePlugin('WebKit built-in PDF',        'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
            ];

            const arr = Object.create(PluginArray.prototype);
            Object.defineProperty(arr, 'length', { get: () => plugins.length });
            plugins.forEach((p, i) => { arr[i] = p; });
            arr.item      = (i) => plugins[i] || null;
            arr.namedItem = (n) => plugins.find(p => p.name === n) || null;
            arr.refresh   = () => {};

            Object.defineProperty(navigator, 'plugins', { get: () => arr, configurable: true });
        })();
        """,

        # 4. Idiomas
        """
        Object.defineProperty(navigator, 'languages', {
            get: () => ['pt-BR', 'pt', 'en-US', 'en'],
            configurable: true
        });
        """,

        # 5. Plataforma, hardware e memória
        """
        Object.defineProperty(navigator, 'platform',            { get: () => 'Win32', configurable: true });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8,       configurable: true });
        Object.defineProperty(navigator, 'deviceMemory',        { get: () => 8,       configurable: true });
        """,

        # 6. Screen — profundidade de cor real
        """
        Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
        Object.defineProperty(screen, 'pixelDepth',  { get: () => 24, configurable: true });
        """,

        # 7. Permissions API — impede detecção via notifications probe
        """
        (function() {
            const _orig = window.navigator.permissions.query;
            window.navigator.permissions.query = (p) =>
                p.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : _orig(p);
        })();
        """,

        # 8. Canvas noise — varia o fingerprint entre sessões sem quebrar renderização
        f"""
        (function() {{
            const nr = {noise_r}, ng = {noise_g}, nb = {noise_b};
            const _orig = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function(type, attrs) {{
                const ctx = _orig.call(this, type, attrs);
                if (ctx && type === '2d') {{
                    const _origGID = ctx.getImageData.bind(ctx);
                    ctx.getImageData = function(x, y, w, h) {{
                        const d = _origGID(x, y, w, h);
                        for (let i = 0; i < d.data.length; i += 4) {{
                            d.data[i]   = Math.min(255, d.data[i]   + nr);
                            d.data[i+1] = Math.min(255, d.data[i+1] + ng);
                            d.data[i+2] = Math.min(255, d.data[i+2] + nb);
                        }}
                        return d;
                    }};
                }}
                return ctx;
            }};
        }})();
        """,

        # 9. WebGL — vendor/renderer realistas de hardware Intel
        """
        (function() {
            const _orig = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {
                if (p === 37445) return 'Google Inc. (Intel)';
                if (p === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                return _orig.call(this, p);
            };
        })();
        """,

        # 10. Remove variáveis globais que o ChromeDriver/Selenium injeta
        """
        (function() {
            const cdcVars = [
                'cdc_adoQpoasnfa76pfcZLmcfl_Array',
                'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
                'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
                '$cdc_asdjflasutopfhvcZLmcfl_',
                '__webdriver_script_fn',
                '__driver_evaluate',
                '__webdriver_evaluate',
                '__selenium_evaluate',
                '__fxdriver_evaluate',
                '__driver_unwrapped',
                '__webdriver_unwrapped',
                '__selenium_unwrapped',
                '__fxdriver_unwrapped',
            ];
            cdcVars.forEach(v => { try { delete window[v]; } catch(e) {} });
        })();
        """,

        # 11. Connection API — simula conexão Wi-Fi normal
        """
        if (!navigator.connection) {
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    rtt: 50, type: 'wifi', saveData: false,
                    downlink: 10, effectiveType: '4g'
                }),
                configurable: true
            });
        }
        """,
    ]

    if janela_oculta():
        # Janela fora da tela fica "hidden" e com coordenadas negativas — o site da Amil
        # trata isso como robô e devolve "nenhum prestador". Fingir janela visível.
        scripts.append("""
        Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });
        Object.defineProperty(document, 'hidden',          { get: () => false,     configurable: true });
        document.hasFocus = () => true;
        Object.defineProperty(window, 'screenX',    { get: () => 0, configurable: true });
        Object.defineProperty(window, 'screenY',    { get: () => 0, configurable: true });
        Object.defineProperty(window, 'screenLeft', { get: () => 0, configurable: true });
        Object.defineProperty(window, 'screenTop',  { get: () => 0, configurable: true });
        """)

    try:
        for script in scripts:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": script},
            )
    except Exception as e:
        print(f"⚠️ Stealth não pôde ser aplicado: {e}")
