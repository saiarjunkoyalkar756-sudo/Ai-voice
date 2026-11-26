<?php
/**
 * Voicely Call Logs & Voice Analytics Console
 */
require_once __DIR__ . '/db.php';
$db = getDb();

session_start();
$ADMIN_SECRET = 'VoicelyAdmin2026!';

$authenticated = false;
if (isset($_SESSION['voicely_auth']) && $_SESSION['voicely_auth'] === true) {
    $authenticated = true;
} elseif (isset($_REQUEST['token']) && $_REQUEST['token'] === $ADMIN_SECRET) {
    $_SESSION['voicely_auth'] = true;
    $authenticated = true;
}

$calls = [];
if ($authenticated && $db) {
    $stmt = $db->query("SELECT * FROM voicely_call_logs ORDER BY id DESC LIMIT 100");
    $calls = $stmt->fetchAll(PDO::FETCH_ASSOC);
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Voicely Voice Telemetry — Call Logs</title>
  <link rel="icon" type="image/png" href="/favicon.png">
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card: #111827;
      --border: #1f2937;
      --emerald: #10b981;
      --text: #f9fafb;
      --muted: #9ca3af;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Geist', sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon { width: 40px; height: 40px; border-radius: 10px; background: linear-gradient(135deg, #10b981, #047857); display: flex; align-items: center; justify-content: center; font-weight: 700; color: white; font-size: 18px; }
    .brand-title { font-size: 20px; font-weight: 700; }
    .brand-subtitle { font-size: 12px; color: var(--muted); }
    .btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; text-decoration: none; border: none; background: var(--border); color: var(--text); }
    .btn:hover { background: #374151; }
    .table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
    .table th { background: #151d2f; padding: 14px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: var(--muted); }
    .table td { padding: 14px 16px; border-top: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
    .badge { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; }
    .badge-inbound { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
    .badge-outbound { background: rgba(16, 185, 129, 0.2); color: #34d399; }
  </style>
</head>
<body>

<div class="container">
  <div class="header">
    <div class="brand">
      <div class="brand-icon">Vy</div>
      <div>
        <div class="brand-title">Voicely Telephony Logs</div>
        <div class="brand-subtitle">Automated Call Transcripts & Telemetry · Rahul (Maruthi Furnitures Concierge)</div>
      </div>
    </div>
    <div>
      <a href="leads_admin.php" class="btn">📋 View Leads CRM</a>
      <a href="export_leads.php?token=VoicelyExport2026!" class="btn">📥 Export CSV</a>
    </div>
  </div>

  <?php if (!$authenticated): ?>
    <div style="max-width: 400px; margin: 80px auto; background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 32px; text-align: center;">
      <h3 style="margin-bottom: 16px;">Authentication Required</h3>
      <a href="leads_admin.php" class="btn" style="background: var(--emerald); color: #042f2e;">Sign In through CRM Console</a>
    </div>
  <?php else: ?>
    <table class="table">
      <thead>
        <tr>
          <th>Call ID</th>
          <th>Caller Phone</th>
          <th>Direction</th>
          <th>Duration</th>
          <th>Sentiment</th>
          <th>Summary / Transcript</th>
          <th>Date & Time</th>
        </tr>
      </thead>
      <tbody>
        <?php if (empty($calls)): ?>
          <tr><td colspan="7" style="text-align: center; padding: 40px; color: var(--muted);">No calls recorded yet.</td></tr>
        <?php else: ?>
          <?php foreach ($calls as $c): ?>
            <tr>
              <td><code><?php echo htmlspecialchars($c['call_id']); ?></code></td>
              <td><strong><?php echo htmlspecialchars($c['phone_number']); ?></strong></td>
              <td><span class="badge badge-<?php echo strtolower($c['direction']); ?>"><?php echo strtoupper($c['direction']); ?></span></td>
              <td><?php echo intval($c['duration_seconds']); ?>s</td>
              <td><span style="color: var(--emerald);"><?php echo htmlspecialchars($c['sentiment']); ?></span></td>
              <td style="max-width: 400px; font-size: 12px; color: #d1d5db;"><?php echo htmlspecialchars($c['summary']); ?></td>
              <td style="color: var(--muted); font-size: 12px;"><?php echo htmlspecialchars($c['created_at']); ?></td>
            </tr>
          <?php endforeach; ?>
        <?php endif; ?>
      </tbody>
    </table>
  <?php endif; ?>
</div>

</body>
</html>
