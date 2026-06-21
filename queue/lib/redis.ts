// Conexión compartida a Redis para BullMQ (la usan tanto los productores como
// los workers). Centralizar la conexión acá evita abrir una por cada cola y nos
// da un único lugar donde configurarla.
import { Redis } from "ioredis";

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

// maxRetriesPerRequest: null es OBLIGATORIO para los workers de BullMQ.
// Hace que ioredis reintente cada comando indefinidamente mientras Redis no esté
// disponible, en vez de tirar error. Así el worker sobrevive a cortes de Redis y
// sigue procesando cuando vuelve. Si NO se setea, BullMQ lanza una excepción.
export const connection = new Redis(url, {
  maxRetriesPerRequest: null,
});

// Si la conexión falla (URL mal, password mal, Redis caído), lo logueamos en vez
// de dejar que el evento quede sin manejar.
connection.on("error", (err: Error) => {
  console.error("[redis] error de conexión:", err.message);
});
