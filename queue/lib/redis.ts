// Opciones de conexión a Redis para BullMQ.
//
// En vez de crear el cliente ioredis a mano, exportamos un OBJETO de opciones y
// dejamos que BullMQ construya la conexión internamente. Esto evita el "dual
// package hazard" (dos copias de ioredis en node_modules con tipos incompatibles)
// y hace que BullMQ se encargue solo de los requisitos de conexión de los workers.

// El secreto NO se hardcodea: se lee de REDIS_URL, que vive en ~/.hermes/.env
// (chmod 600) en el VPS. En local podés exportarla en tu shell para probar.
const url = process.env.REDIS_URL;

if (!url) {
  // Fail-closed: sin URL no arrancamos. Mejor un error claro que un fallo raro
  // de conexión más adelante.
  throw new Error(
    "Falta REDIS_URL en el entorno. Cargala en ~/.hermes/.env " +
      "(ver deploy/install-notes.md, sección 9).",
  );
}

// Parseamos la URL (redis://:password@host:port) en sus componentes.
const parsed = new URL(url);

export const connectionOptions = {
  host: parsed.hostname,
  port: parsed.port ? Number(parsed.port) : 6379,
  // Con requirepass no hay usuario; ioredis usa solo la password. decodeURIComponent
  // por si la password trae caracteres escapados en la URL.
  username: parsed.username ? decodeURIComponent(parsed.username) : undefined,
  password: parsed.password ? decodeURIComponent(parsed.password) : undefined,
  // Obligatorio para los workers de BullMQ: reintentar cada comando para siempre
  // mientras Redis no esté disponible, en vez de tirar error. Inofensivo para la cola.
  maxRetriesPerRequest: null,
};
