# Deck de capacidades · Malaparte Analytica

Versión imprimible (PDF) de la presentación de capacidades, pensada para enviar a
clientes: jefes de campaña y estructuras partidarias que todavía deciden sin
medición propia. El arco del documento va de diagnóstico → urgencia → capacidades →
resultado → oferta → cierre.

## Archivos

| Archivo | Qué es |
|---|---|
| `deck.html` | Fuente del deck. 26 slides de 1280×720 px (16:9, = 13,333″ × 7,5″). Editar acá. |
| `assets/fonts.css` | Instrument Serif, Inter e IBM Plex Mono embebidas en base64 (sin dependencia de red). |
| `build.sh` | Genera el PDF con Chromium headless. |
| `Malaparte_Analytica_Capacidades.pdf` | Entregable final, 26 páginas, fuentes embebidas. |

## Regenerar el PDF

```bash
./build.sh                      # busca Chromium/Chrome en las rutas habituales
./build.sh /ruta/a/chrome       # o se le pasa el binario
OUT=otro_nombre.pdf ./build.sh  # cambiar el nombre de salida
```

El PDF sale sin encabezados ni pies del navegador y con una página por slide.

## Antes de enviarlo a un cliente

1. **Datos de contacto** — slide 25 (`Cierre`) tiene placeholders marcados en el HTML
   con el comentario `⚠︎ EDITAR`: correo, teléfono/WhatsApp y sitio.
2. **Aritmética del margen** — slide 5 usa un distrito de ejemplo de 120.000 votos
   efectivos. Si el deck va a un cliente concreto, reemplazar por su padrón real
   (la nota al pie ya aclara que es aritmética, no pronóstico).
3. **Puertas de entrada** — slide 20 no lleva precios: se cotiza por distrito, olas
   y calendario.

## Estructura del deck

| # | Slide | Función |
|---|---|---|
| 01 | Portada | Promesa central |
| 02 | Grilla de capacidades | Índice / mapa de las 12 capacidades |
| 03 | Punto de partida | Espejo: con qué información decide hoy el cliente |
| 04 | Las cuatro preguntas | Brecha entre lo que se cree y lo que se sabe |
| 05 | Aritmética del margen | Cuánto cuesta el error |
| 06 | Costo de decidir a ciegas | Seis pérdidas invisibles |
| 07 | Ventana de corrección | Cuenta regresiva de lo reversible |
| 08 | La asimetría | Adivinar vs. medir con el mismo presupuesto |
| 09 | El sistema | Las seis capas conectadas |
| 10-16 | Capacidades | Research · CAWI · Historia · Big Data · NOMOS · War Room · Operación |
| 17 | Ritmo semanal | Cómo se trabaja, día por día |
| 18 | Diez preguntas | Resultado concreto y su fuente |
| 19 | Uso interno | Qué recibe cada área, incluida la estructura territorial |
| 20 | Puertas de entrada | Cuatro módulos, uno recomendado |
| 21 | Primeros 21 días | Puesta en marcha, reducción de riesgo |
| 22 | Método | Trazabilidad |
| 23 | Operación responsable | Lo que no hacemos / lo que sí prometemos |
| 24 | Dos caminos | Costo de esperar |
| 25 | Próximo paso | Cierre y contacto |
| 26 | Contratapa | Confidencialidad |
