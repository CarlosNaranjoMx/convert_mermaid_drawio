# convert_mermaid_drawio

Un script en Python para convertir diagramas Mermaid (`.mmd`) en un archivo `draw.io` (`.drawio`).

## Características

- Convierte un archivo `.mmd` en un `.drawio` con una sola pestaña.
- Convierte una carpeta con múltiples `.mmd` en un único `.drawio` con varias pestañas.
- Soporta diagramas de tipo `flowchart` / `graph` con direcciones `LR`, `RL`, `TB`, `TD`, `BT`.
- Admite nodos rectangulares, redondeados, elípticos, rombos y cilindros.
- Admite aristas con flechas, líneas sólidas, punteadas y etiquetas.
- Admite subgraph (contenedores anidados) y clases de estilo básicas.

## Uso

```bash
python convert_mmd_draw.py <archivo.mmd> [-o salida.drawio]
python convert_mmd_draw.py <carpeta> [-o salida.drawio]
```

### Ejemplos

- Convertir un archivo Mermaid:
  ```bash
  python convert_mmd_draw.py diagrama.mmd -o diagrama.drawio
  ```
- Convertir todos los `.mmd` de una carpeta en un solo archivo `draw.io`:
  ```bash
  python convert_mmd_draw.py carpeta_mmd -o salida.drawio
  ```

## Notas

- El script genera un único archivo `draw.io` con pestañas para cada diagrama si se procesa una carpeta.
- La sintaxis soportada es una variante práctica de Mermaid enfocada en diagramas de flujo.
