// Definición de las colas de BullMQ. Una cola es una "lista de trabajos" en Redis;
// los productores le agregan jobs y los workers los consumen. Productores y workers
// deben referirse a la MISMA cola por su nombre.
import { Queue } from "bullmq";

import { connectionOptions } from "./redis.js";

// Nombre de la cola de "postear un comentario en GitHub". Se exporta como constante
// para que productor y worker usen exactamente el mismo string (evita typos).
export const POST_COMMENT_QUEUE = "post-comment";

// La cola en sí. Comparte la conexión definida en redis.ts.
export const postCommentQueue = new Queue(POST_COMMENT_QUEUE, {
  connection: connectionOptions,
  // Opciones por defecto que heredan TODOS los jobs de esta cola.
  defaultJobOptions: {
    // Reintentos ante fallos transitorios (ej. la API de GitHub responde 5xx o
    // hay un corte de red). Tras 5 intentos fallidos, el job se marca como fallido.
    attempts: 5,
    // Backoff exponencial entre reintentos: ~5s, 10s, 20s, 40s. Evita martillar a
    // GitHub cuando algo está caído y respeta los rate limits.
    backoff: { type: "exponential", delay: 5000 },
    // Higiene de Redis (el VPS tiene 1GB): los completados se borran rápido; los
    // fallidos se conservan 24h para poder investigarlos.
    removeOnComplete: { age: 3600, count: 100 },
    removeOnFail: { age: 24 * 3600 },
  },
});
