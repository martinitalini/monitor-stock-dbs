"""Monitor de stock para un producto de DBS Chile.

Sólo informa 'disponible' con evidencia explícita del producto principal.
No considera títulos, botones ni existencias de productos relacionados.
"""

import json
import os
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

PRODUCT_URL = "https://dbs.cl/maquillaje-sets-twist-n-twinkle-holiday-calendario-de-adviento"
PRODUCT_NAME = "KIKO Milano — Twist 'N Twinkle Holiday Calendario de Adviento"
STATE_FILE = Path("estado.json")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"


def normalize(value):
    raw = unicodedata.normalize("NFKD", str(value).lower())
    return "".join(ch for ch in raw if not unicodedata.combining(ch))


def interpret_availability(value):
    # Solo interpretar señales explícitas de inventario, no frases genéricas.
    val = normalize(value).strip().rstrip("/")
    if val in ("instock", "https://schema.org/instock", "http://schema.org/instock"):
        return "disponible"
    if val in ("outofstock", "soldout", "https://schema.org/outofstock", "http://schema.org/outofstock"):
        return "agotado"
    return None


def matches_product(value):
    val = normalize(value)
    return "twist" in val and "twinkle" in val and any(
        word in val for word in ("advent", "adviento", "calendario")
    )


def walk_jsonld(node):
    if isinstance(node, list):
        for part in node:
            yield from walk_jsonld(part)
    elif isinstance(node, dict):
        yield node
        if "@graph" in node:
            yield from walk_jsonld(node["@graph"])


def detect_stock(html):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if not (matches_product(title) or matches_product(page_title)):
        return None, "La página no parece corresponder al producto buscado."

    # 1) Magento / tiendas similares: etiquetas visibles del producto principal.
    main = soup.select_one(".product-info-main")
    if main:
        unavailable = main.select_one(
            ".stock.unavailable, .stock.out-of-stock, .stock.outofstock, "
            ".stock.sold-out, .stock.soldout"
        )
        available = main.select_one(".stock.available, .stock.in-stock, .stock.instock")
        if unavailable and available:
            return None, "Señales contradictorias de stock."
        if unavailable:
            return "agotado", "Indicador de inventario del producto (agotado)."
        if available:
            return "disponible", "Indicador de inventario del producto (disponible)."

        for tag in main.select('[itemprop="availability"], meta[property="product:availability"]'):
            raw = tag.get("content") or tag.get("href") or tag.get_text(" ", strip=True)
            found = interpret_availability(raw)
            if found:
                return found, "Metadato de inventario del producto."

    # 2) Datos estructurados JSON-LD del producto EXACTO.
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in walk_jsonld(data):
            typ = normalize(obj.get("@type", ""))
            if "product" not in typ or not matches_product(obj.get("name", "")):
                continue
            offers = obj.get("offers", [])
            for offer in offers if isinstance(offers, list) else [offers]:
                if isinstance(offer, dict):
                    found = interpret_availability(offer.get("availability", ""))
                    if found:
                        return found, "Datos estructurados del producto."

    # 3) Botón principal de compra (no botones de productos recomendados).
    if main:
        button = main.select_one("#product-addtocart-button")
        if button:
            disabled = button.has_attr("disabled") or normalize(button.get("aria-disabled", "")) == "true"
            if not disabled and any(x in normalize(button.get_text(" ", strip=True))
                                    for x in ("carrito", "comprar", "cart")):
                return "disponible", "Botón principal de compra habilitado."

        stock = main.select_one(".product-info-stock-sku .stock")
        if stock:
            stock_text = normalize(stock.get_text(" ", strip=True))
            if any(x in stock_text for x in ("agotado", "sin stock", "no disponible")):
                return "agotado", "Texto de inventario del producto."
            if "disponible" in stock_text or "en stock" in stock_text:
                return "disponible", "Texto de inventario del producto."

    return None, "DBS no entregó una señal de disponibilidad reconocible."


def inspect_product():
    r = requests.get(
        PRODUCT_URL,
        timeout=25,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.7",
        },
    )
    if r.status_code != 200:
        return None, f"DBS devolvió HTTP {r.status_code}."
    if urlparse(r.url).hostname not in ("dbs.cl", "www.dbs.cl"):
        return None, "DBS redirigió fuera de su dominio."
    return detect_stock(r.text)


def notify_discord(message):
    if not WEBHOOK.startswith("https://discord.com/api/webhooks/"):
        raise RuntimeError("Falta configurar el secreto DISCORD_WEBHOOK_URL de Discord.")
    # Nunca mostrar ni imprimir el enlace privado del webhook.
    try:
        r = requests.post(WEBHOOK, json={"content": message}, timeout=15)
    except requests.RequestException:
        raise RuntimeError("No se pudo contactar el webhook de Discord.") from None
    if not (200 <= r.status_code < 300):
        raise RuntimeError(f"Discord rechazó la notificación (HTTP {r.status_code}).")


def main():
    if not WEBHOOK.startswith("https://discord.com/api/webhooks/"):
        raise RuntimeError("Configura el secreto DISCORD_WEBHOOK_URL antes de iniciar.")

    try:
        new_status, reason = inspect_product()
    except requests.RequestException:
        new_status, reason = None, "No se pudo conectar a DBS."

    print(f"Resultado de DBS: {new_status or 'desconocido'}. Motivo: {reason}")

    if TEST_MODE:
        readable = new_status or "DESCONOCIDO — revisar registro de Actions"
        notify_discord(
            "🧪 **PRUEBA del monitor DBS**\n"
            f"Producto: **{PRODUCT_NAME}**\n"
            f"Estado detectado: **{readable.upper()}**\n"
            f"Detalle: {reason}\n{PRODUCT_URL}"
        )
        print("Prueba de Discord enviada.")

    if new_status is None:
        # Nunca confundir un bloqueo, error 404 o página distinta con 'hay stock'.
        print("ERROR: no se pudo confirmar el inventario. No se enviará alerta de stock.")
        return 1

    previous_status = None
    if STATE_FILE.exists():
        try:
            previous_status = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("estado")
        except (json.JSONDecodeError, OSError):
            pass

    if new_status == "disponible" and previous_status != "disponible" and not TEST_MODE:
        notify_discord(
            "🚨 **¡STOCK DISPONIBLE EN DBS!** 🚨\n"
            f"**{PRODUCT_NAME}**\n"
            "Revisa el producto cuanto antes:\n"
            f"{PRODUCT_URL}"
        )
        print("Alerta de reposición enviada a Discord.")
    elif new_status == "disponible" and previous_status != "disponible" and TEST_MODE:
        print("El producto está disponible; ya se informó en el mensaje de prueba.")
    else:
        print("Sin nueva reposición de stock; no se enviarán alertas repetidas.")

    if previous_status != new_status:
        STATE_FILE.write_text(
            json.dumps({"estado": new_status}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("Se guardará el nuevo estado para las siguientes revisiones.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
