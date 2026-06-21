# Notas de instalación — Fase 1 (Hermes vivo por Discord en el VPS)

Pasos para desplegar el gateway de Hermes en el VPS. Los **PASOS MANUALES** los hace
el humano. Los archivos versionados de este repo (`config/hermes/config.yaml`,
`deploy/systemd/hermes-gateway.service`) se copian al VPS según estas notas.

> Estado: el VPS está **pendiente de provisionar** (Oracle pide tarjeta; pospuesto).
> Cuando lo tengas, seguí estos pasos en orden.

---

## 0. Provisionar el VPS (manual)

- Proveedor recomendado: **Oracle Cloud "Always Free"** (ARM Ampere; fallback AMD x86 o GCP `e2-micro`).
- SO: **Ubuntu 22.04 LTS**.
- SSH key a pegar al crear la instancia: tu clave pública `~/.ssh/id_ed25519.pub`.
- Anotar la **IP pública** y la **arquitectura** (ARM o x86).

Conexión:
```powershell
ssh ubuntu@TU_IP_PUBLICA
```

---

## 1. Preparar el sistema y un usuario no-root (en el VPS)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git

# Usuario dedicado para correr el bot (NO-root).
sudo adduser --disabled-password --gecos "" hermes
sudo mkdir -p /home/hermes/.ssh
sudo cp ~/.ssh/authorized_keys /home/hermes/.ssh/
sudo chown -R hermes:hermes /home/hermes/.ssh
sudo chmod 700 /home/hermes/.ssh && sudo chmod 600 /home/hermes/.ssh/authorized_keys

# Directorio de trabajo del agente (terminal.cwd del config.yaml).
sudo -u hermes mkdir -p /home/hermes/work
```

---

## 2. Instalar Hermes (como usuario hermes)

```bash
sudo su - hermes
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

- Si falla por arquitectura ARM → reprovisionar en instancia x86.
- Verificar instalación y **anotar la ruta del binario**:
  ```bash
  which hermes      # usar esta ruta en el ExecStart del service (paso 6)
  ls -la ~/.hermes/ # debe existir el directorio de config
  ```

---

## 3. Crear el bot de Discord (manual, fuera del VPS)

1. discord.com/developers/applications → **New Application**.
2. **Bot → Reset Token → copiar** el token (paso 5).
3. **Bot → Privileged Gateway Intents →** activar **Message Content Intent**.
4. **OAuth2 → URL Generator →** scope `bot`; permisos: Send Messages, Read Message
   History, View Channels. Abrir la URL e **invitar el bot al servidor**.
5. Obtener tu **ID de usuario**: Discord → Ajustes → Avanzado → **Modo desarrollador** ON;
   click derecho en tu usuario → **Copiar ID**. (Varios IDs → separados por coma.)

---

## 4. Conseguir la API key de OpenRouter (manual)

- openrouter.ai → **Keys → Create Key** → copiar.
- Cargar crédito (el modelo `moonshotai/kimi-k2.6` se factura por uso).

---

## 5. Cargar los secrets en el VPS

Como usuario `hermes`, crear `~/.hermes/.env` con los valores reales
(plantilla de variables en `deploy/.env.example`):

```bash
nano ~/.hermes/.env
```
```
OPENROUTER_API_KEY=sk-or-...
DISCORD_BOT_TOKEN=...
DISCORD_ALLOWED_USERS=123456789012345678
```
```bash
chmod 600 ~/.hermes/.env
```

---

## 6. Instalar la config y el servicio

```bash
# Copiar la config del repo a la ubicación que lee Hermes.
cp config/hermes/config.yaml ~/.hermes/config.yaml

# RECONCILIAR nombres de campos: comparar config.yaml del repo con el que generó el
# instalador. Si algún nombre difiere (api_key_env, token_env, allowed_users_env,
# sandbox.backend, etc.), ajustar y registrar el cambio en ADR-0002.

# Confirmar/ajustar la ruta del binario en ExecStart (paso 2: `which hermes`).
sudo cp deploy/systemd/hermes-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-gateway
```

---

## 7. Validar (checklist de cierre de la Fase 1)

```bash
systemctl status hermes-gateway            # debe estar active (running)
journalctl -u hermes-gateway -f            # logs en vivo
```

- [ ] El bot responde a un mensaje de un usuario **en** la allowlist.
- [ ] Un usuario **fuera** de la allowlist es denegado.
- [ ] `sudo systemctl restart hermes-gateway` recupera el servicio.
- [ ] Un **reboot** del VPS (`sudo reboot`) recupera el servicio sin intervención.
- [ ] Logs accesibles (`journalctl` y/o `~/.hermes/logs/`).
- [ ] `~/.hermes/.env` con `chmod 600`.

Cuando todo pase: actualizar `HANDOFF.md`, confirmar ADR-0002 y mergear la fase a `main`.

---

## 8. Conectar el MCP de GitHub — solo lectura (Fase 3a)

> **PASO MANUAL (humano):** generar el PAT de GitHub (fine-grained), scopeado a:
> Contents=read, Pull requests=read/write, Issues=read/write, Metadata=read,
> Actions=read. **Sin** Administration ni Workflows:write (sin merge/push/force-push).
> Cargarlo en `~/.hermes/.env` como `GITHUB_PAT` (chmod 600).

El MCP **no** se declara en `config.yaml`: se gestiona con el CLI `hermes mcp`.

```bash
# Como usuario hermes:
sudo su - hermes

# Agregar el MCP de GitHub. Comillas SIMPLES en el env para guardar la referencia
# literal ${GITHUB_PAT} (Hermes la resuelve en runtime desde ~/.hermes/.env; el
# token NO queda hardcodeado en la config del MCP).
hermes mcp add github --command npx \
  --env GITHUB_PERSONAL_ACCESS_TOKEN='${GITHUB_PAT}' \
  --args -y @modelcontextprotocol/server-github

# GUARDRAIL: dejar el MCP en SOLO-LECTURA. Lanza un selector interactivo.
# Responder 'select' y DESACTIVAR (SPACE) las 12 tools de escritura:
#   create_or_update_file, create_repository, push_files, create_issue,
#   create_pull_request, fork_repository, create_branch, update_issue,
#   add_issue_comment, create_pull_request_review, merge_pull_request,
#   update_pull_request_branch
# Dejar tildadas SOLO las 14 de lectura. ENTER para confirmar.
hermes mcp configure github

# Verificar: debe decir "14 selected · enabled".
hermes mcp list

# Reiniciar el gateway para tomar los cambios (como ubuntu).
exit
sudo systemctl restart hermes-gateway
```

**Validación (3a):** desde Discord, pedirle a Hermes que lea un archivo del repo
(p. ej. `get_file_contents` sobre `CLAUDE.md`). Debe devolver el contenido real.

---

## 9. Instalar y asegurar Redis (prerequisito de la Fase 3b)

> **PASO MANUAL (humano).** Redis es el almacén que usa BullMQ para la cola de jobs.
> Sin Redis no hay cola → no hay worker → no hay approval gate. Por eso es bloqueante
> para 3b. El worker corre en la MISMA VPS, así que Redis NO necesita exponerse a
> internet: lo dejamos escuchando solo en localhost + password (defensa en profundidad).

```bash
# Como ubuntu, instalar.
sudo apt install redis-server

# Asegurarlo: editar el config.
sudo nano /etc/redis/redis.conf
```

En `redis.conf`, verificar/ajustar dos directivas (buscar con Ctrl+W):

1. **`bind 127.0.0.1 ::1`** — solo localhost. El default de Ubuntu ya suele venir así;
   NO usar `0.0.0.0` (eso lo expondría a internet en una IP pública = comprometido en horas).
2. **`requirepass <clave>`** — descomentar y poner una clave fuerte. Generar con
   `openssl rand -hex 32` (formato **hex**, no base64: hex es URL-safe y no rompe el
   `REDIS_URL`; base64 trae `+` `/` `=` que tienen significado especial en una URL).

```bash
# Aplicar y verificar.
sudo systemctl restart redis-server
redis-cli ping                      # esperado: (error) NOAUTH Authentication required.
redis-cli -a '<clave>' ping         # esperado: PONG
```

Cargar la URL de conexión en el `.env` de Hermes (como usuario `hermes`):

```bash
sudo su - hermes
nano ~/.hermes/.env
#   añadir:  REDIS_URL=redis://:<clave>@127.0.0.1:6379
#   (el ':' va solo, sin usuario: Redis con requirepass no usa username)
chmod 600 ~/.hermes/.env

# Verificar la URL completa de punta a punta (como la leerá BullMQ).
redis-cli -u "$(grep REDIS_URL ~/.hermes/.env | cut -d= -f2-)" ping   # esperado: PONG
```

**Validación (Redis):** `redis-cli ping` sin clave da `NOAUTH`; con la URL del `.env`
da `PONG`. Con eso, la Fase 3b queda desbloqueada.
