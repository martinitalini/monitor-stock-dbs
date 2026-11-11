# Monitor de stock DBS -> Discord (gratis)

Producto: https://dbs.cl/maquillaje-sets-twist-n-twinkle-holiday-calendario-de-adviento

## Preparación

1. Crea un webhook en Discord, dentro de Ajustes del servidor > Integraciones > Webhooks. Copia la URL, pero no la publiques.
2. Crea un repositorio **público** en GitHub llamado `monitor-stock-dbs`.
3. Sube estos archivos respetando las rutas. La carpeta `.github/workflows/` es necesaria.
4. En Settings > Secrets and variables > Actions, crea un **Repository secret** con nombre `DISCORD_WEBHOOK_URL` y pega la URL del webhook.
5. En Settings > Actions > General, establece **Workflow permissions** en **Read and write permissions**. Guarda los cambios.
6. En Actions > Monitor stock DBS a Discord > Run workflow, pulsa el botón para una comprobación manual.
7. Revisa el canal de Discord y el registro de la ejecución. Si el resultado es DESCONOCIDO/rojo, DBS podría estar bloqueando los accesos automáticos o haber cambiado su estructura. No presupongas que el monitor detecta el stock hasta ver un resultado válido.

## Funcionamiento

- Una ejecución programada se solicita cada 5 minutos; GitHub puede retrasar o saltar ejecuciones.
- Envía una alerta solo cuando cambia de agotado a disponible. La primera ejecución, si encuentra disponible, también avisa.
- La ejecución manual manda un **mensaje de prueba** con el estado detectado; no manda una alerta de reposición adicional.
- Guarda el último estado en `estado.json` por medio de un commit automático de GitHub Actions.
- No requiere tu PC encendido.
- GitHub puede desactivar los workflows programados de repositorios públicos tras 60 días sin actividad. Si eso ocurre, reactívalos.
- El método analiza indicadores de la página. DBS podría exigir JavaScript, bloquear la solicitud o cambiar su HTML; en ese caso, habrá que ajustar el detector.

## Seguridad

La URL privada de Discord va en el secreto `DISCORD_WEBHOOK_URL`, NO dentro de archivos del repositorio ni compartida por chat.

## Detener el monitor

En GitHub: Actions > Monitor stock DBS a Discord > menú de tres puntos > Disable workflow.
