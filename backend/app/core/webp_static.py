"""StaticFiles con negociacion de contenido WebP.

Sirve automaticamente la version .webp de una imagen estatica (.jpg/.jpeg/.png)
cuando:

  1. El navegador anuncia soporte WebP en la cabecera `Accept`, y
  2. Existe un archivo hermano con el mismo nombre pero extension .webp.

Delegacion segura:
- Si no hay .webp hermano o el navegador no lo soporta, se sirve el original.
- Los crawlers sociales (Facebook, WhatsApp, Twitter...) NO aceptan WebP, por lo
  que el `og:image` en .jpg sigue funcionando sin cambios en las plantillas.

Uso (main.py):
    app.mount("/static/frontend", WebPStaticFiles(directory=...), name=...)
"""
from __future__ import annotations

import os

from starlette.datastructures import Headers
from starlette.staticfiles import StaticFiles

# Extensiones susceptibles de tener version WebP hermana.
_RASTER_EXTS = (".jpg", ".jpeg", ".png")


class WebPStaticFiles(StaticFiles):
    """StaticFiles con reescritura transparente a .webp segun `Accept`."""

    async def get_response(self, path: str, scope):
        headers = Headers(scope=scope)
        accept = headers.get("accept", "")
        if "image/webp" in accept and path.lower().endswith(_RASTER_EXTS):
            webp_path = path.rsplit(".", 1)[0] + ".webp"
            # Comprobar existencia de forma version-agnostica (lookup_path es
            # async en Starlette <=0.25 y sync en >=0.26; os.path funciona siempre).
            base = os.path.realpath(self.directory)
            full = os.path.realpath(os.path.join(base, webp_path))
            if full.startswith(base + os.sep) and os.path.isfile(full):
                path = webp_path
        return await super().get_response(path, scope)