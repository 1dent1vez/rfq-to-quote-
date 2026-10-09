# Guía del operador · DEMO local

**Solo clientes y pedidos ficticios.** No escriba contactos reales, RFC, contraseñas ni datos confidenciales. Actor es una etiqueta demo, no un inicio de sesión. Precios, costos, IVA, stock y reservas son simulados; no se envía correo.

## Arranque

Desde el directorio del proyecto ejecute `./run-demo.sh` y abra `http://127.0.0.1:8000/`. La primera instalación necesita internet para dependencias; el flujo no necesita un modelo ni un proveedor activo. Para detener, Ctrl+C en la terminal del servidor.

## Ejemplo completo

1. Mantenga **Taller Rivera (ficticio)** y el mensaje `2 GP-149; entrega urgente`.
2. Puede usar captura manual inicial o activar **Sugerencias offline (no LLM)**. El parser solo reconoce referencias literales y cantidades numéricas; no entiende la entrega ni asigna vehículo.
3. **Recibir solicitud** guarda la evidencia original. Repetir el mismo identificador y contenido devuelve la misma solicitud; cambiar contenido con ese identificador produce conflicto. Para otro pedido use **Nueva solicitud**.
4. En **Revisión humana**, seleccione explícitamente **GP-149** y cantidad **2**. No seleccione el SKU solo porque aparece una sugerencia.
5. Escriba **Vendedor demo** en actor, un motivo de confirmación y evidencia suplementaria, por ejemplo: “Cliente ficticio confirma dos GP-149 por referencia; entrega local, sin fecha prometida”.
6. Clasifique `entrega urgente` como **Contexto sustantivo confirmado**, con motivo “Entrega local acordada, sin promesa de plazo”. No lo marque como saludo.
7. **Guardar revisión y evidencia** conserva la solicitud original y añade una revisión. Luego **Crear borrador**: subtotal MXN 300.00, IVA supuesto 48.00 y total 348.00 con la tabla inicial.
8. Revise versión, reglas y catálogo. Marque **Acepto la versión…** y **Aprobar y reservar DEMO**. Se vuelven a verificar stock, margen y precio dentro de la transacción. La reserva local es de dos piezas y no se repite por reintento exacto.
9. Descargue HTML imprimible o CSV. El HTML puede abrirse e imprimirse / guardarse como PDF desde el navegador. No es factura ni cotización enviada al cliente.

## Datos faltantes y vehículos

Si falta cantidad, déjela pendiente hasta recibir una confirmación ficticia y escríbala como evidencia suplementaria. Si un fragmento contiene otro artículo, agréguelo con **Agregar artículo de evidencia suplementaria**, seleccione su referencia/cantidad y vincule el fragmento a la línea.

Para una consulta por vehículo, seleccione **Por vehículo, verificar fuente** y capture marca, modelo, año y motor explícitos. Ejemplo con fuente: `Nissan`, `Versa`, `2018`, `1.6` y GP-149. Para 2023 el GP-149 no tiene declaración en este subconjunto; GP-91 cubre 2020–2025, pero no se sustituye automáticamente: el humano confirma el alcance y registra la decisión.

Cabina tiene dos alternativas GAC/GAF por intervalo; no se elige automáticamente ni se afirma equivalencia. La fuente dice aplicación de catálogo, no garantía de instalación. Consulta por referencia no certifica vehículo. Fuera del subconjunto no significa incompatibilidad; queda sin resolver hasta otra confirmación respaldada.

Cada fragmento requiere clasificación y motivo. Solo saludos literales como “hola” o “gracias” pueden ser **Saludo / no sustantivo**. Restricciones, entregas, cantidades globales y vehículo necesitan resolución explícita, no ignorarse.

## Adjuntos admitidos

- TXT o CSV con nombre seguro, UTF-8 estricto (BOM opcional), máximo 20,000 bytes y 100 líneas. No PDF, Excel, imágenes ni OCR.
- Con un adjunto seleccionado, su texto es la entrada original; el textarea no se mezcla automáticamente. Quite el archivo del control para volver a texto pegado.
- CSV: encabezado exacto `reference,quantity`; cantidades positivas enteras o vacías para revisión. Máximo 99 filas de datos.

```text
reference,quantity
GP-149,2
GA-306,1
```

No se reparan guiones de referencias. `GP149` no se convierte automáticamente en `GP-149`; el operador debe confirmar/corregir mediante evidencia nueva. En CSV las líneas son captura explícita, no inferencia de lenguaje natural.

## Reproducir bloqueos comerciales

Abra **Operador DEMO · inventario y reinicio**. Escriba actor/motivo, elija GP-149 y guarde cambios con dos decimales (`160.00`). La tabla operacional es independiente del catálogo del fabricante.

| Prueba | Acción | Resultado |
|---|---|---|
| Precio obsoleto | Cree borrador con precio 150.00; luego cámbielo a 160.00 y trate de aprobar | 409; debe regenerar borrador |
| Sin stock | Pida 2; ponga existencias en 1 antes de crear/aprobar borrador | Bloqueo; ninguna reserva parcial |
| Margen insuficiente | Precio 160.00, costo 159.00 | Bloqueo de margen; no hay descuento automático |
| Versión obsoleta | Abra misma solicitud en dos pestañas, guarde revisión en una y accione la otra | 409; recargue versión guardada |
| Competencia de stock | Dos solicitudes por 2 con disponibilidad 2; apruebe ambas | Solo una aprobación/reserva puede ganar |
| Aprobada | Intente editar o regenerar | Solo lectura; descarga sigue usando el snapshot aprobado |

La tabla se actualiza tras cambios de versión, pero el editor de inventario conserva la versión de sus campos. Si el editor quedó obsoleto, recargue la tabla y use **Recargar artículo en editor (descartar cambios)**, luego revise y vuelva a guardar. Recargar una solicitud descarta ediciones no guardadas.

## Historial y reinicio

El historial, evidencia, versiones y auditoría quedan en SQLite. La auditoría operacional muestra actor, motivo y antes/después de reservas, cambios de precio y stock.

Para empezar de nuevo, escriba exactamente **RESET PORTFOLIO DEMO**, actor y motivo, y pulse **Reiniciar solo portfolio DEMO**. Borra las solicitudes/reservas de la base nueva y restaura valores sintéticos; conserva el evento y la auditoría operacional. No borra estudios ni presupuestos de modelos. Esto es intencionalmente destructivo dentro del demo y no debe usarse con datos reales.

La IA experimental sigue fuera del flujo por sus resultados insuficientes. No reinicie presupuestos ni active llamadas al modelo para hacer funcionar esta guía.
