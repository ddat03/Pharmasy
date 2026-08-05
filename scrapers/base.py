"""Base compartida para todos los scrapers: rate limit, reintentos,
user-agent, guardado de crudos.

TODO (fase 2 del Orden de construcción): implementar al construir el primer
scraper end-to-end. Reglas a respetar, ver
Boveda Farmacia/Conceptos/Scraping respetuoso.md:
  - 1 petición cada 5-10s con jitter
  - user-agent identificable
  - nunca evadir bloqueos activos (403/429 sistemático -> blocked_from_ci)
  - preferir siempre endpoints JSON internos sobre parseo de HTML
"""
