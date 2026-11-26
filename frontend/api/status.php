<?php
/**
 * Voicely Real-Time Health & System Telemetry Endpoint
 */
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

$start_time = microtime(true);
$response = [
    'brand' => 'Voicely AI Systems',
    'timestamp' => date('c'),
    'status' => 'operational',
    'services' => []
];

// 1. MySQL Health Check
try {
    require_once __DIR__ . '/db.php';
    $db_start = microtime(true);
    $stmt = $pdo->query("SELECT 1");
    $db_latency_ms = round((microtime(true) - $db_start) * 1000, 2);

    $lead_count = $pdo->query("SELECT COUNT(*) FROM voicely_contacts")->fetchColumn();
    $call_count = $pdo->query("SELECT COUNT(*) FROM voicely_call_logs")->fetchColumn();

    $response['services']['mysql_database'] = [
        'status' => 'operational',
        'latency_ms' => $db_latency_ms,
        'records' => [
            'contacts' => intval($lead_count),
            'call_logs' => intval($call_count)
        ]
    ];
} catch (Exception $e) {
    $response['status'] = 'degraded';
    $response['services']['mysql_database'] = [
        'status' => 'outage',
        'error' => $e->getMessage()
    ];
}

// 2. EC2 Voice Engine Health Check
$ec2_ip = "3.27.169.179";
$ec2_port = 80;
$socket_start = microtime(true);
$fp = @fsockopen($ec2_ip, $ec2_port, $errno, $errstr, 2);
if ($fp) {
    fclose($fp);
    $ec2_latency_ms = round((microtime(true) - $socket_start) * 1000, 2);
    $response['services']['voice_inference_engine'] = [
        'status' => 'operational',
        'host' => 'AWS ap-southeast-2 (Sydney)',
        'latency_ms' => $ec2_latency_ms,
        'active_agent' => 'Rahul · Maruthi Furnitures Concierge'
    ];
} else {
    $response['services']['voice_inference_engine'] = [
        'status' => 'warning',
        'message' => 'Connection timed out or firewall restricted'
    ];
}

// 3. System Storage & Cron Status
$backup_dir = '/home/apima263/backups';
$last_backup = 'None';
if (is_dir($backup_dir)) {
    $files = scandir($backup_dir, SCANDIR_SORT_DESCENDING);
    foreach ($files as $f) {
        if (strpos($f, '.sql.gz') !== false) {
            $last_backup = $f . ' (' . date('Y-m-d H:i:s', filemtime($backup_dir . '/' . $f)) . ')';
            break;
        }
    }
}

$response['services']['backup_automation'] = [
    'status' => 'operational',
    'cron_schedule' => 'Nightly at 00:00 UTC',
    'last_backup' => $last_backup
];

$response['total_check_time_ms'] = round((microtime(true) - $start_time) * 1000, 2);

echo json_encode($response, JSON_PRETTY_PRINT);
