/** Simula la latencia de red. Solo para los servicios que hoy usan mocks. */
export const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
