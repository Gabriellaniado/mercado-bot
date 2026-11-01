# Bot de mercado

Revisa el S&P 500, materias primas (oro, plata, petróleo, uranio, etc.) y acciones argentinas y brasileñas, y manda por Telegram un informe con:

- **Panorama** del día (S&P 500, Bovespa, oro, petróleo, uranio).
- **Análisis de mercado**: sectores mejores y peores que el S&P 500 y posibles rotaciones (por ejemplo, de semiconductores a software), calculados solo con precios. Indican que un sector le ganó a otro, no por qué.
- **Mercado local**: MSCI Merval en pesos y en dólares CCL, riesgo país, dólares y las acciones del panel que más suben y bajan.
- **Grandes movimientos**: hasta 3 variaciones fuera de lo normal (según la volatilidad de los últimos 20 días), primero las que tienen CEDEAR. Del S&P 500 solo entran empresas de más de US$100.000 millones (`min_market_cap_usd_bn`).
- **A revisar**: hasta 3 activos con CEDEAR muy por debajo de su máximo anual y sobrevendidos (RSI) o cerca de su mínimo de 52 semanas.
- **Contexto de cada activo**: si reaccionó a un balance, si acompaña a su sector, ventas, margen, valuación, opinión de analistas y qué falta confirmar.
- **Noticias**: usa **solo fuentes de una lista confiable** (`trusted_sources` en `config.yaml`). Si no hay titulares de esas fuentes, lo dice en lugar de inventar una causa.

> Son señales automáticas para revisar. No son una recomendación de inversión.

## Puesta en marcha

### 1. Crear el bot de Telegram
1. En Telegram, hablá con **@BotFather**, enviá `/newbot` y seguí los pasos. Te da un **token**.
2. Mandale cualquier mensaje a tu bot nuevo.
3. Abrí `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` en el navegador y buscá `"chat":{"id": ...}`. Ese número es tu **chat id**.

### 2. Correrlo en tu computadora
```bash
python -m venv .venv
.venv\Scripts\activate          # en Windows
pip install -r requirements-dev.txt
copy .env.example .env          # completá el token y el chat id
python -m bot.main --dry-run    # imprime el informe sin enviarlo
python -m bot.main              # lo envía por Telegram
python -m bot.main --dry-run --brief        # versión corta, para sumarle un resumen
python -m bot.main --send-file informe.txt  # envía un informe ya redactado
```

### 3. Correrlo desde GitHub
El workflow `daily.yml` se lanza a mano desde la pestaña **Actions** y no tiene horario. Necesita los secretos `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en **Settings → Secrets and variables → Actions**. `ANTHROPIC_API_KEY` es opcional: sin ella, el informe sale sin resumen.

## Desarrollo
```bash
pytest               # tests; falla si la cobertura baja de 80%
ruff check .         # errores y malas prácticas
ruff format .        # formato
```
Los tests no usan internet ni mandan mensajes. El workflow `ci.yml` corre estos controles en cada push.

## Configuración
Todo se edita en `config.yaml`:
- **`cedears`**: cruce con la [lista de Banco Comafi](https://www.comafi.com.ar/custodiaglobal/2483-Programas-Cedear.cedearnote.note.aspx) al 30/09/2026. Actualizala cada tanto. `URA` y `EWZ` no están en esa lista.
- **`feeds`**: los medios cambian sus URLs. Si un feed falla o viene vacío, el bot avisa en el log y sigue.
- **`trusted_sources`**: fuentes aceptadas para los titulares.
- **`signals`** y **`market_analysis`**: umbrales, cantidad de activos y pares de rotación.

## Limitaciones
- El índice local es el MSCI Merval de BYMA: el servicio gratuito publica el S&P Merval en cero, y en Yahoo está desactualizado. No es el mismo índice que el S&P Merval. Los activos cuyos precios quedan más de 5 días atrás se descartan y se avisa en el log.
- Los precios y balances vienen de Yahoo Finance mediante `yfinance` (no oficial): pueden tener demoras, huecos o datos ajustados.
- Las acciones argentinas y brasileñas se miden por sus ADRs en dólares, no por su cotización local.
- Las acciones del panel local se miden en pesos, y la variación del Merval en dólares es aproximada: usa el CCL informado por argentinadatos.
- El uranio se sigue con el ETF `URA`, porque Yahoo no ofrece el precio spot.
- El bot detecta si un activo reaccionó a un balance y si superó lo esperado en ganancia por acción, pero no lee las previsiones de la empresa.

## Estructura
```
bot/
  main.py          # orquesta todo y línea de comandos
  universe.py      # lista de activos (S&P 500 desde Wikipedia + config)
  prices.py        # descarga de precios
  local_market.py  # dólares, riesgo país, Merval y panel en pesos
  analysis.py      # panorama, sectores, rotaciones y selección de activos
  signals.py       # cálculos: RSI, grandes movimientos, oportunidades
  fundamentals.py  # contexto de cada activo: balance, sector, negocio, valuación
  news.py          # noticias de Yahoo y RSS, filtradas por fuentes confiables
  summarize.py     # resumen opcional con la API de Anthropic
  report.py        # arma el texto del informe
  telegram.py      # envío por Telegram
tests/             # pytest, sin red
```
