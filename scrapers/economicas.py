"""Scraper de Farmacias Económicas.

El sitio propio (farmaciaseconomicas.com.ec) no tiene catálogo funcional
(WooCommerce inactivo, 404 en productos y en su Store API). Decisión
confirmada 2026-08-05: scrapear en su lugar la vitrina de Farmacias
Económicas dentro de Rappi (rappi.com.ec/tiendas/marca-farmacias-economicas
lista las sucursales; robots.txt no restringe /tiendas/; catálogo en HTML
plano, sin login). Riesgo residual: cláusula genérica de ToS de Rappi contra
manipulación de datos, aceptado conscientemente.

TODO (fase 5 del Orden de construcción): implementar iterando sucursales
listadas en la página "marca", extrayendo producto/precio por tienda.

Ver Boveda Farmacia/Entidades/Farmacias Económicas.md y
Boveda Farmacia/Entidades/Rappi.md.
"""
