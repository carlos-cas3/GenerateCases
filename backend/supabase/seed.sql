-- Documento de prueba para la Fase 1. El objeto de Storage no se crea: el
-- pipeline simulado no lee el archivo.
insert into public.documents (id, filename, file_type, size_bytes, storage_path, checksum, uploaded_at)
values (
    '6f9d1c2e-0a4b-4c8d-9e1f-2b3c4d5e6f70',
    'historias-release-1.txt',
    'txt',
    4821,
    'seed/6f9d1c2e-0a4b-4c8d-9e1f-2b3c4d5e6f70/historias-release-1.txt',
    '9b74c9897bac770ffc029102a200c5de',
    '2026-10-25T12:00:00Z'
)
on conflict (id) do nothing;
