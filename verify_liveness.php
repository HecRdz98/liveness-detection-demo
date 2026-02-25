<?php
/**
 * verify_liveness.php
 * Backend PHP que actúa como puente entre el frontend y el script Python de análisis.
 * Recibe frames en base64 + challenge, llama a Python via proc_open y devuelve el resultado.
 */

// --- Headers: JSON y CORS ---
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Manejar preflight CORS
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

// Solo aceptar método POST
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Método no permitido. Solo se acepta POST.']);
    exit;
}

// --- Leer y parsear JSON del body ---
$raw_input = file_get_contents('php://input');

if (empty($raw_input)) {
    http_response_code(400);
    echo json_encode(['error' => 'Cuerpo de la solicitud vacío.']);
    exit;
}

$data = json_decode($raw_input, true);

if (json_last_error() !== JSON_ERROR_NONE) {
    http_response_code(400);
    echo json_encode(['error' => 'JSON inválido: ' . json_last_error_msg()]);
    exit;
}

// --- Validar campos requeridos ---
$frames   = $data['frames']    ?? null;
$challenge = $data['challenge'] ?? null;

if (!is_array($frames) || count($frames) < 5) {
    http_response_code(400);
    echo json_encode(['error' => 'Se requiere el campo "frames" con al menos 5 elementos.']);
    exit;
}

if (empty($challenge) || !is_string($challenge)) {
    http_response_code(400);
    echo json_encode(['error' => 'El campo "challenge" es requerido y debe ser texto.']);
    exit;
}

// Limitar a máximo 25 frames para evitar sobrecarga
$data['frames'] = array_slice($frames, 0, 25);
$frames_enviados = count($data['frames']);

// --- Preparar payload JSON para Python ---
$payload = json_encode($data);

// --- Ruta del script Python ---
$script_path = __DIR__ . '/verify_liveness.py';

if (!file_exists($script_path)) {
    http_response_code(500);
    echo json_encode(['error' => 'Script Python no encontrado en: ' . $script_path]);
    exit;
}

// --- Detectar binario de Python disponible (python3 primero, luego python) ---
$python_bin = null;

exec('python3 --version 2>&1', $out3, $rc3);
if ($rc3 === 0) {
    $python_bin = 'python3';
} else {
    exec('python --version 2>&1', $out2, $rc2);
    if ($rc2 === 0) {
        $python_bin = 'python';
    }
}

if (!$python_bin) {
    http_response_code(500);
    echo json_encode([
        'error' => 'Python no encontrado en el PATH del sistema. Instala Python 3.8+ y asegúrate de que esté en el PATH.'
    ]);
    exit;
}

// --- Abrir proceso Python con proc_open (más seguro que shell_exec) ---
$descriptors = [
    0 => ['pipe', 'r'],  // stdin  → escribimos el JSON
    1 => ['pipe', 'w'],  // stdout → leemos el resultado
    2 => ['pipe', 'w'],  // stderr → capturamos errores
];

$cmd     = $python_bin . ' ' . escapeshellarg($script_path);
$process = proc_open($cmd, $descriptors, $pipes);

if (!is_resource($process)) {
    http_response_code(500);
    echo json_encode(['error' => 'No se pudo iniciar el proceso Python. Verifica que proc_open esté habilitado en PHP.']);
    exit;
}

// Escribir JSON a stdin de Python y cerrar el pipe para señalar EOF
fwrite($pipes[0], $payload);
fclose($pipes[0]);

// Leer resultado desde stdout
$stdout = stream_get_contents($pipes[1]);
fclose($pipes[1]);

// Leer posibles errores desde stderr
$stderr = stream_get_contents($pipes[2]);
fclose($pipes[2]);

// Obtener código de salida del proceso
$exit_code = proc_close($process);

// --- Preparar directorio y archivo de logs ---
$log_dir = __DIR__ . '/logs';
if (!is_dir($log_dir)) {
    mkdir($log_dir, 0755, true);
}

// Parsear la respuesta de Python
$resultado = json_decode($stdout, true);

// --- Guardar log con fecha, challenge, resultado y detalle ---
$log_line = sprintf(
    "[%s] Challenge: %-35s | Frames: %2d | Passed: %-3s | Reason: %s\n",
    date('Y-m-d H:i:s'),
    $challenge,
    $resultado['frames_analyzed'] ?? 0,
    ($resultado['passed'] ?? false) ? 'SI' : 'NO',
    $resultado['reason'] ?? 'N/A'
);
file_put_contents($log_dir . '/liveness.log', $log_line, FILE_APPEND | LOCK_EX);

// --- Verificar si hubo error en Python ---
if ($exit_code !== 0 || $resultado === null) {
    // Registrar error en log
    $error_log = sprintf(
        "[%s] ERROR: exit_code=%d | stderr=%s | stdout=%s\n",
        date('Y-m-d H:i:s'),
        $exit_code,
        trim($stderr),
        trim($stdout)
    );
    file_put_contents($log_dir . '/liveness.log', $error_log, FILE_APPEND | LOCK_EX);

    http_response_code(500);
    echo json_encode([
        'error'     => 'Error durante el análisis de liveness.',
        'detail'    => $stderr ?: ($stdout ?: 'Sin detalle de error.'),
        'exit_code' => $exit_code
    ]);
    exit;
}

// --- Devolver resultado al frontend ---
echo json_encode($resultado);
