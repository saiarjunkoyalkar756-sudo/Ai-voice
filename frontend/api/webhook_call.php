<?php
/**
 * Voicely Live Telephony Webhook Receiver
 * Ingests call events from Twilio & LiveKit into voicely_call_logs
 */
header('Content-Type: application/json');
require_once __DIR__ . '/db.php';

$db = getDb();
if (!$db) {
    http_response_code(500);
    echo json_encode(['status' => 'error', 'message' => 'Database connection failed']);
    exit;
}

// Accept JSON or form POST
$raw_input = file_get_contents('php://input');
$payload = json_decode($raw_input, true);

if (!$payload) {
    $payload = $_POST;
}

$call_id = $payload['CallSid'] ?? $payload['call_id'] ?? $payload['sid'] ?? ('CALL-' . time() . '-' . rand(1000, 9999));
$phone_number = $payload['From'] ?? $payload['phone_number'] ?? $payload['caller'] ?? 'Anonymous';
$direction = $payload['Direction'] ?? $payload['direction'] ?? 'inbound';
$duration = intval($payload['CallDuration'] ?? $payload['duration_seconds'] ?? $payload['duration'] ?? 0);
$sentiment = $payload['sentiment'] ?? 'positive';
$recording_url = $payload['RecordingUrl'] ?? $payload['recording_url'] ?? '';
$summary = $payload['Transcript'] ?? $payload['summary'] ?? ($payload['notes'] ?? 'Call processed by Rahul · Maruthi Furnitures Concierge');

try {
    $stmt = $db->prepare("
        INSERT INTO voicely_call_logs (call_id, phone_number, direction, duration_seconds, sentiment, summary, recording_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, NOW())
        ON DUPLICATE KEY UPDATE 
            duration_seconds = VALUES(duration_seconds),
            sentiment = VALUES(sentiment),
            summary = VALUES(summary),
            recording_url = VALUES(recording_url)
    ");
    $stmt->execute([
        $call_id,
        $phone_number,
        $direction,
        $duration,
        $sentiment,
        $summary,
        $recording_url
    ]);

    echo json_encode([
        'status' => 'success',
        'message' => 'Call log recorded successfully',
        'call_id' => $call_id,
        'client' => 'Maruthi Furnitures & Mattresses'
    ]);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        'status' => 'error',
        'message' => $e->getMessage()
    ]);
}
