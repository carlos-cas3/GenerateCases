# Observaciones sobre `fase1_5_pipeline.md`

## Propósito

Este documento reúne observaciones y ajustes recomendados para revisar
`fase1_5_pipeline.md` antes de empezar la implementación de la fase 1.5.

**No sustituye al plan operativo ni afirma que las propuestas ya estén
implementadas.** Cada punto debe contrastarse con el contrato y el
comportamiento real del backend cuando corresponda.

## Observaciones y ajustes recomendados

### 1. P7: retirar de los criterios de aceptación obligatorios

P7 no debería ser un criterio de aceptación obligatorio de esta fase.
Registrar su evaluación o implementación como una posible ampliación o
trabajo futuro.

Esto no significa eliminar sin más las referencias a `p7` del código o
de la documentación: primero hay que comprobar qué consumidores dependen
del catálogo de etapas y cómo responde actualmente el backend.

### 2. Recuperación de una generación: ajustarla a la API existente

Revisar la recuperación obligatoria mediante `?g=<uuid>` y definir una
estrategia compatible con los endpoints y el comportamiento que la API
ya ofrece. No introducir un requisito de recuperación más estricto sin
confirmar que sea necesario para la integración.

El UUID puede conservarse como **identificador técnico interno** para
consultar o recuperar la generación. No debe presentarse al usuario como
si fuera el nombre del documento.

En la interfaz, mostrar el **nombre del documento** asociado a la
generación, cuando la API lo proporcione. El UUID puede seguir
utilizándose internamente y, si hace falta, en la URL o en herramientas
de diagnóstico.

### 3. Una sola generación activa en la interfaz

Aclarar que la interfaz debe permitir el seguimiento de una sola
generación activa a la vez y prevenir el doble envío accidental.
Mientras la generación que se está siguiendo permanezca en estado
activo, el botón para iniciar otra debe comportarse de acuerdo con esa
regla.

Esto es una regla de interfaz. No debe describirse como garantía global
de concurrencia del backend: el propio plan indica que esa política del
backend está pendiente de definición.

### 4. Reinicio del backend: marcar las generaciones activas como fallidas

Si el backend se reinicia mientras hay una generación activa, esta debe quedar marcada como `failed`, registrando como motivo la interrupción del backend, por ejemplo: `Generación interrumpida por el reinicio del backend`.

La interfaz debe mostrar el estado fallido y el motivo cuando esté disponible, sin intentar reanudar automáticamente la generación. El usuario podrá iniciar una nueva ejecución manualmente.

Para implementar este comportamiento, verificar que el backend pueda identificar las generaciones que estaban activas antes del reinicio y actualizar su estado. Si la información de las ejecuciones se pierde al reiniciar el servicio, será necesario evaluar cómo conservarla para poder registrar el fallo.

### 5. Polling y reintentos: mantener una política sencilla

Distinguir explícitamente entre:

-   **Fallo de una consulta de estado:** por ejemplo, un error de red o
    una respuesta temporalmente no disponible.
-   **Fallo de la generación:** el backend informa que la generación
    terminó con estado `failed`.

Un error al consultar no demuestra por sí solo que la generación haya
fallado. La interfaz debe evitar convertir automáticamente un problema
de comunicación en un fallo de ejecución.

Para esta fase, definir una política de polling y recuperación acotada y
comprensible. Los intervalos y el número exacto de reintentos deben
considerarse decisiones de implementación, no requisitos de la API,
salvo que exista una necesidad comprobada. Evitar añadir complejidad
innecesaria antes de validar el flujo básico.

### 6. Manejadores de errores: revisar antes de añadir

Inspeccionar los manejadores de errores y el formato de respuesta que ya
existen en el backend. Reutilizar el contrato actual y modificar o
añadir manejadores solo cuando se compruebe que la integración lo
necesita.

En particular, verificar que un cambio no reemplace errores de dominio
específicos por un error genérico ni altere sus códigos HTTP o su
significado. Las respuestas que actualmente no siguen el formato
esperado deben documentarse y tratarse de manera compatible.

### 7. Vitest: separar la incorporación de la integración obligatoria

Si el frontend todavía no utiliza Vitest, mover su incorporación a una
fase específica de pruebas del frontend o dejarla como tarea posterior.
No convertir la instalación de una nueva infraestructura de pruebas en
requisito de la integración principal sin justificarlo.

Si se decide no incorporar Vitest en esta fase, dejar claro que las
verificaciones correspondientes deberán realizarse mediante el checklist
manual existente. No presentar pruebas automatizadas como ejecutadas si
no se han implementado y corrido.

### 8. Clasificar las tareas por prioridad y alcance

Etiquetar las tareas para distinguir qué es imprescindible en esta fase
y qué puede aplazarse. Se recomienda usar estas categorías:

-   **Integración obligatoria:** conectar la interfaz con los endpoints
    existentes y representar correctamente los datos y estados que
    devuelve la API.
-   **Robustez necesaria:** prevenir dobles envíos, gestionar la
    cancelación de consultas y diferenciar errores de comunicación de
    fallos reales de la generación.
-   **Mejora posterior:** mejoras de experiencia o mecanismos
    adicionales cuya necesidad todavía no se ha demostrado.
-   **Trabajo futuro / posible ampliación:** elementos fuera del alcance
    de la fase, incluida la evaluación o implementación de P7 si no es
    necesaria para completar la integración actual.

La clasificación definitiva debe basarse en los criterios de aceptación
acordados y en lo que la API soporta realmente.

## Resumen de cambios propuestos

Antes de programar, revisar `fase1_5_pipeline.md` para:

1.  Retirar P7 de los criterios de aceptación obligatorios y
    documentarlo como posible ampliación.
2.  Ajustar la recuperación a la API existente; conservar el UUID como
    identificador interno y mostrar al usuario el nombre del documento.
3.  Establecer una sola generación activa en la interfaz y prevenir el
    doble envío, sin asumir una garantía de concurrencia del backend.
4.  Confirmar la política real de las generaciones ante el reinicio del
    backend antes de exigir un estado final concreto.
5.  Simplificar el polling y los reintentos, separando errores de
    consulta y fallos de generación.
6.  Revisar los manejadores y el contrato de errores existentes antes de
    añadir otros.
7.  Tratar Vitest como una fase específica de pruebas del frontend si
    todavía no forma parte del proyecto.
8.  Clasificar las tareas por prioridad y alcance.

**Criterio rector:** la fase 1.5 debe integrar el frontend con las
capacidades que el backend ofrece realmente. Las decisiones que
impliquen un contrato nuevo, garantías no verificadas o trabajo
adicional deben confirmarse y clasificarse antes de convertirlas en
requisitos.
