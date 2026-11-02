# Bot de mercado

Revisa el S&P 500, materias primas (oro, plata, petróleo, uranio, etc.) y acciones argentinas y brasileñas, y manda por Telegram un informe con:

- **Panorama** del día (S&P 500, Bovespa, oro, petróleo, uranio).
- **Análisis de mercado**: sectores mejores y peores que el S&P 500 y posibles rotaciones (por ejemplo, de semiconductores a software), calculados solo con precios. Indican que un sector le ganó a otro, no por qué.
- **Mercado local**: MSCI Merval en pesos y en dólares CCL, riesgo país, dólares y las acciones del panel que más suben y bajan.
- **Grandes movimientos**: hasta 3 variaciones fuera de lo normal (según la volatilidad de los últimos 20 días), primero las que tienen CEDEAR. Del S&P 500 solo entran empresas de más de US$100.000 millones (`min_market_cap_usd_bn`).
- **Oportunidades** (solo activos con CEDEAR), con tres tipos de señal:
  - **Compra por rebote**: al menos 15% bajo su máximo anual y sobrevendido (RSI ≤ 35) o a menos de 10% de su mínimo de 52 semanas.
  - **Compra por ruptura**: llega a un máximo de 52 semanas con volumen 1,5 veces mayor al habitual.
  - **Venta**: sobrecomprado (RSI ≥ 70) y a menos de 5% de su máximo anual.
  - **Cruces de medias móviles**: cruce dorado y cruce de la muerte (media de 50 contra la de 200) y cruce de la media de 20 contra la de 50, solo si ocurrieron en las últimas 3 ruedas.
  - **Figuras chartistas**: doble techo y doble piso confirmados (el precio rompe el piso o el techo entre los dos picos) y ruptura de un rango lateral de 20 ruedas.
  - **Soportes y resistencias de tendencia**: traza la recta que une mínimos cada vez más altos (o máximos cada vez más bajos) y exige al menos tres toques. Marca el rebote sobre la línea o su ruptura, e indica el nivel aproximado.
  - **Opinión de analistas**: cada señal se contrasta con el precio objetivo y la recomendación media de Yahoo (si hay 5 analistas o más). Si coinciden, la señal sube en el informe y dice "analistas a favor"; si la contradicen, baja y dice "analistas en contra". Nunca se descarta una señal por esto.

  Si un activo junta varias señales del mismo lado, se suman los puntajes y sube en el informe. Las figuras se detectan con reglas simples y pueden fallar: sirven para mirar el gráfico, no para confirmarlo. Se apagan con `chart_signals: false`.

  Los umbrales y la cantidad de señales (`max_opportunities`, `max_sell_signals`) se cambian en `config.yaml`. Con valores más exigentes el bot es más cauteloso; con valores más bajos, más arriesgado.
- **Contexto de cada activo**: si reaccionó a un balance, si acompaña a su sector, ventas, margen, valuación, opinión de analistas y qué falta confirmar.
- **Noticias**: usa **solo fuentes de una lista confiable** (`trusted_sources` en `config.yaml`). Si no hay titulares de esas fuentes, lo dice en lugar de inventar una causa.

> El informe del bot son señales automáticas para revisar, no una recomendación de inversión. La rutina diaria le agrega recomendaciones y precios objetivo generados por IA, que pueden tener errores.

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
python -m bot.main --analysis analisis.json # informe final con el análisis de la rutina
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

## Análisis de la rutina diaria
La rutina investiga las causas y escribe un JSON. El bot lo valida y arma el mensaje, así el formato no depende del agente:
```json
{
  "global": "Una línea sobre el mercado de EE.UU.",
  "local": "Una línea sobre el mercado argentino.",
  "assets": {
    "INTC": {
      "recommendation": "mantener",
      "confidence": "media",
      "target": 72.5,
      "target_basis": "Cómo se calculó",
      "cause": "Causa breve",
      "source": "Fuente"
    }
  }
}
```
`recommendation` admite `comprar`, `mantener`, `vender` o `null`, y `confidence` admite `alta`, `media` o `baja`. `target` es opcional, pero exige `target_basis`.

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
  report.py        # informe sin IA, en texto
  analyst.py       # valida el análisis de la rutina y arma el informe final
  telegram.py      # envío por Telegram
tests/             # pytest, sin red
```
