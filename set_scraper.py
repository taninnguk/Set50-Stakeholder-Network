from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


SET_BASE_URL = "https://www.set.or.th"


class BrowserFetchError(RuntimeError):
    """Raised when SET data cannot be fetched from the browser session."""


@dataclass(frozen=True)
class StockInfo:
    symbol: str
    name: str = ""
    market: str = ""


@dataclass(frozen=True)
class ShareholderRecord:
    symbol: str
    company_name: str
    shareholder: str
    rank: int | None
    shares: int | None
    percent: float | None
    as_of: str
    ca_type: str
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_symbol(symbol: Any) -> str:
    return re.sub(r"\s+", "", str(symbol or "")).upper()


def parse_symbol_input(text: str) -> list[str]:
    seen: set[str] = set()
    symbols: list[str] = []
    for item in re.split(r"[\s,;]+", text or ""):
        symbol = normalize_symbol(item)
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _pick_first_text(data: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = normalize_space(data.get(key))
        if value:
            return value
    return ""


def extract_stocks_from_composition(
    payload: dict[str, Any] | list[Any],
    index_symbol: str = "SET50",
) -> list[StockInfo]:
    """Extract stock symbols from SET index composition payloads.

    SET has adjusted response shapes over time. Prefer explicit stockInfos
    arrays, then fall back to symbol-bearing dictionaries.
    """

    index_symbol = normalize_symbol(index_symbol)
    seen: set[str] = set()
    stocks: list[StockInfo] = []

    def append_stock(item: dict[str, Any]) -> None:
        symbol = normalize_symbol(item.get("symbol") or item.get("securitySymbol"))
        if not symbol or symbol == index_symbol or symbol in seen:
            return

        level = normalize_space(item.get("level")).upper()
        if level in {"INDEX", "INDUSTRY", "SECTOR"}:
            return

        name = _pick_first_text(
            item,
            [
                "nameTH",
                "nameEN",
                "securityName",
                "securityNameTH",
                "securityNameEN",
                "companyName",
                "companyNameTH",
                "companyNameEN",
                "fullName",
            ],
        )
        market = _pick_first_text(item, ["market", "marketName"])
        seen.add(symbol)
        stocks.append(StockInfo(symbol=symbol, name=name, market=market))

    def walk(obj: Any) -> None:
        if isinstance(obj, list):
            for value in obj:
                walk(value)
            return

        if not isinstance(obj, dict):
            return

        for key in ("stockInfos", "stocks", "securities", "items"):
            value = obj.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        append_stock(item)
                    walk(item)

        if not stocks and "symbol" in obj:
            append_stock(obj)

        for value in obj.values():
            if isinstance(value, (dict, list)):
                walk(value)

    root: Any = payload
    if isinstance(payload, dict) and payload.get("composition"):
        root = payload["composition"]

    walk(root)
    return stocks


def parse_shareholder_payload(
    symbol: str,
    company_name: str,
    payload: dict[str, Any],
    top_n: int = 5,
) -> list[ShareholderRecord]:
    shareholders = payload.get("majorShareholders") or payload.get("shareholders") or []
    if not isinstance(shareholders, list):
        return []

    as_of = normalize_space(
        payload.get("bookCloseDate")
        or payload.get("asOfDate")
        or payload.get("asOf")
        or ""
    )
    ca_type = normalize_space(payload.get("caType") or "")
    records: list[ShareholderRecord] = []

    for index, item in enumerate(shareholders[:top_n], start=1):
        if not isinstance(item, dict):
            continue

        name = _pick_first_text(
            item,
            ["name", "shareholder", "shareholderName", "holderName"],
        )
        if not name:
            continue

        rank = parse_int(item.get("order") or item.get("rank") or index)
        shares = parse_int(
            item.get("numberOfShare")
            or item.get("numberOfShares")
            or item.get("shares")
        )
        percent = parse_float(
            item.get("percentOfShare")
            or item.get("percentShare")
            or item.get("percent")
        )
        source_url = f"{SET_BASE_URL}/th/market/product/stock/quote/{symbol}/major-shareholders"
        records.append(
            ShareholderRecord(
                symbol=normalize_symbol(symbol),
                company_name=company_name,
                shareholder=name,
                rank=rank,
                shares=shares,
                percent=percent,
                as_of=as_of,
                ca_type=ca_type,
                source_url=source_url,
            )
        )

    return records


class SetScraper:
    def __init__(
        self,
        browser: str = "chrome",
        headless: bool = True,
        lang: str = "th",
        request_timeout_seconds: int = 35,
        page_timeout_seconds: int = 30,
        delay_seconds: float = 0.2,
    ) -> None:
        self.browser = browser.lower()
        self.headless = headless
        self.lang = "th" if lang.lower().startswith("th") else "en"
        self.request_timeout_seconds = request_timeout_seconds
        self.page_timeout_seconds = page_timeout_seconds
        self.delay_seconds = delay_seconds
        self.driver: webdriver.Chrome | webdriver.Edge | None = None
        self._warmed = False

    def __enter__(self) -> "SetScraper":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def start(self) -> None:
        if self.driver:
            return

        try:
            if self.browser == "edge":
                options = EdgeOptions()
                self._apply_common_options(options)
                self.driver = webdriver.Edge(options=options)
            else:
                options = ChromeOptions()
                self._apply_common_options(options)
                self.driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            raise BrowserFetchError(
                "Cannot start Selenium browser. Install Chrome or Edge, then try again."
            ) from exc

        self.driver.set_page_load_timeout(self.page_timeout_seconds)
        self.driver.set_script_timeout(self.request_timeout_seconds + 5)

    def close(self) -> None:
        if self.driver:
            self.driver.quit()
        self.driver = None
        self._warmed = False

    def _apply_common_options(self, options: ChromeOptions | EdgeOptions) -> None:
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--lang=th-TH")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.page_load_strategy = "eager"

    def warm_up(self) -> None:
        if self._warmed:
            return
        if not self.driver:
            self.start()
        assert self.driver is not None

        self.driver.get(f"{SET_BASE_URL}/")
        self._wait_until_ready()
        self._accept_cookies()

        home_path = f"/{self.lang}/home"
        self.driver.get(f"{SET_BASE_URL}{home_path}")
        self._wait_until_ready()
        self._accept_cookies()
        self._warmed = True

    def _wait_until_ready(self) -> None:
        assert self.driver is not None
        WebDriverWait(self.driver, self.page_timeout_seconds).until(
            lambda driver: driver.execute_script("return document.readyState")
            in {"interactive", "complete"}
        )

    def _accept_cookies(self) -> None:
        assert self.driver is not None
        selectors = [
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
            "//button[contains(normalize-space(.), 'ยอมรับ')]",
        ]
        for selector in selectors:
            try:
                button = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                button.click()
                return
            except (TimeoutException, WebDriverException):
                continue

    def fetch_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.warm_up()
        assert self.driver is not None

        query = urlencode(params or {})
        if path.startswith("http"):
            url = path
        else:
            url = f"{SET_BASE_URL}{path if path.startswith('/') else '/' + path}"
        if query:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query}"

        script = """
            const url = arguments[0];
            const timeoutMs = arguments[1] * 1000;
            const done = arguments[arguments.length - 1];
            let settled = false;
            const finish = (payload) => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                done(payload);
            };
            const timer = setTimeout(() => {
                finish({ok: false, status: 0, error: "Browser fetch timed out", url});
            }, timeoutMs);
            fetch(url, {
                method: "GET",
                credentials: "include",
                headers: {
                    "accept": "application/json, text/plain, */*"
                }
            }).then(async (response) => {
                const text = await response.text();
                let data = null;
                try {
                    data = JSON.parse(text);
                } catch (error) {
                    data = {"_raw": text};
                }
                finish({ok: response.ok, status: response.status, url: response.url, data});
            }).catch((error) => {
                finish({ok: false, status: 0, error: String(error), url});
            });
        """

        result = self.driver.execute_async_script(
            script,
            url,
            self.request_timeout_seconds,
        )
        if self.delay_seconds:
            time.sleep(self.delay_seconds)

        if not isinstance(result, dict) or not result.get("ok"):
            error = result.get("error") if isinstance(result, dict) else str(result)
            status = result.get("status") if isinstance(result, dict) else "unknown"
            raise BrowserFetchError(f"SET fetch failed ({status}): {error or url}")

        data = result.get("data")
        if isinstance(data, dict) and "_raw" in data:
            raw = str(data.get("_raw") or "")
            if "Incapsula" in raw or "incident ID" in raw:
                raise BrowserFetchError(
                    "SET returned an Incapsula block page. Try a non-headless browser."
                )
            raise BrowserFetchError(f"SET did not return JSON for {url}")

        if not isinstance(data, dict):
            raise BrowserFetchError(f"Unexpected SET response for {url}")
        return data

    def get_index_symbols(self, index_symbol: str = "SET50") -> list[StockInfo]:
        index_symbol = normalize_symbol(index_symbol)
        payload = self.fetch_json(
            f"/api/set/index/{index_symbol}/composition",
            {"lang": self.lang},
        )
        return extract_stocks_from_composition(payload, index_symbol=index_symbol)

    def get_shareholders(
        self,
        symbol: str,
        company_name: str = "",
        top_n: int = 5,
    ) -> list[ShareholderRecord]:
        symbol = normalize_symbol(symbol)
        payload = self.fetch_json(
            f"/api/set/stock/{symbol}/shareholder",
            {"lang": self.lang},
        )
        return parse_shareholder_payload(symbol, company_name, payload, top_n=top_n)
