# Deck de venta · Malaparte Analytica

Presentación de venta en PDF, 16:9, **13 slides** — una idea y un gráfico por lámina.
Pensada para jefes de campaña y estructuras partidarias que todavía deciden sin
medición propia. Arco: problema → costo → urgencia → sistema → capacidades → oferta → cierre.

Además queda la **versión extendida** de 26 slides (`deck_extendido.html`), útil como
material de respaldo o para reuniones largas.

## Archivos

| Archivo | Qué es |
|---|---|
| `slides/NN-*.html` | Una lámina por archivo (`<section class="slide">`). Se editan de forma independiente. |
| `assets/deck.css` | Sistema de diseño: tokens, chrome de lámina, tipografía, componentes. |
| `assets/fonts.css` | Instrument Serif + Inter + IBM Plex Mono embebidas en base64 (render sin red). |
| `assemble.sh` | Concatena `slides/*.html` en `deck.html`. |
| `build.sh` | Ensambla y genera el PDF con Chromium headless. |
| `preview_slide.sh` | Renderiza **una** lámina a PNG para revisarla suelta. |
| `Malaparte_Analytica_Capacidades.pdf` | Entregable principal (13 páginas). |
| `deck_extendido.html` + `..._Extendido.pdf` | Versión larga de 26 slides. |

## Uso

```bash
./build.sh                                  # ensambla deck.html y genera el PDF
./preview_slide.sh slides/06-el-sistema.html # revisar una lámina sola (PNG en /tmp/slidepreview)
SRC=deck_extendido.html OUT=Malaparte_Analytica_Capacidades_Extendido.pdf ./build.sh
```

Cada lámina mide exactamente 1280×720 px (13,33″ × 7,5″). Si `preview_slide.sh` informa
2 páginas, el contenido se desborda.

## Antes de enviarlo a un cliente

1. **Contacto** — slide 13 muestra correo y sitio; están marcados en el HTML con
   `⚠︎ EDITAR` junto con las instrucciones para sumar una tercera columna de WhatsApp.
2. **Aritmética del margen** — slide 03 usa un distrito de ejemplo de 120.000 votos
   efectivos; conviene recalcularlo con el padrón real del cliente.
3. **Gráficos esquemáticos** — las láminas 02, 04, 05, 08, 09, 10 llevan al pie la
   aclaración de que el gráfico es conceptual, esquemático o una vista de ejemplo.
   No sacar esas aclaraciones: son lo que hace defendible el material.
4. **Falta la prueba** — el deck argumenta bien pero no muestra trabajo propio: no hay
   backtesting (medición contra resultado real), ni cantidad de olas o distritos, ni
   quién firma la ficha técnica. Es el agregado de mayor impacto pendiente y necesita
   datos reales de la consultora, no se puede inventar.

## Estructura

| # | Slide | Gráfico protagonista |
|---|---|---|
| 01 | Portada | Marca y claim |
| 02 | Punto de partida | Barras de cobertura informativa por fuente |
| 03 | Aritmética del margen | Dot matrix de 120.000 votos con 1.800 resaltados |
| 04 | Ventana de corrección | Área escalonada del costo de corregir |
| 05 | La asimetría | Dos trayectorias divergentes |
| 06 | El sistema | Diagrama orbital de las seis capacidades |
| 07 | Medición auditable | Embudo del proceso con intervalo declarado |
| 08 | Historia y territorio | Mapa de celdas con mesas bisagra |
| 09 | Micro y nano | Zoom distrito → barrio → célula |
| 10 | NOMOS | Consola móvil de ejemplo |
| 11 | War Room | Ciclo de 24 horas de una ventana |
| 12 | Módulos | Matriz comparativa de contratación |
| 13 | Cierre | Gantt de 21 días + llamada a la acción |
