<?php
/**
 * Voicely Lead Management & CRM Console
 * Protected by Session or Admin Token
 */
require_once __DIR__ . '/db.php';

session_start();

$ADMIN_SECRET = 'VoicelyAdmin2026!';

// Check Authentication
$authenticated = false;
if (isset($_SESSION['voicely_auth']) && $_SESSION['voicely_auth'] === true) {
    $authenticated = true;
} elseif (isset($_REQUEST['token']) && $_REQUEST['token'] === $ADMIN_SECRET) {
    $_SESSION['voicely_auth'] = true;
    $authenticated = true;
} elseif (isset($_POST['password']) && $_POST['password'] === $ADMIN_SECRET) {
    $_SESSION['voicely_auth'] = true;
    $authenticated = true;
}

if (isset($_GET['action']) && $_GET['action'] === 'logout') {
    $_SESSION['voicely_auth'] = false;
    session_destroy();
    header("Location: leads_admin.php");
    exit;
}

// Handle status updates
$msg = '';
if ($authenticated && isset($_POST['update_status']) && isset($_POST['contact_id'])) {
    $cid = intval($_POST['contact_id']);
    $new_status = in_array($_POST['status'], ['new', 'contacted', 'qualified', 'closed']) ? $_POST['status'] : 'new';
    $stmt = $pdo->prepare("UPDATE voicely_contacts SET status = ? WHERE id = ?");
    $stmt->execute([$new_status, $cid]);
    $msg = "Lead #$cid status updated to " . strtoupper($new_status);
}

// Fetch leads if authenticated
$leads = [];
$stats = ['total' => 0, 'new' => 0, 'contacted' => 0, 'qualified' => 0, 'closed' => 0];

if ($authenticated) {
    try {
        $filter = isset($_GET['filter']) ? $_GET['filter'] : 'all';
        if ($filter !== 'all' && in_array($filter, ['new', 'contacted', 'qualified', 'closed'])) {
            $stmt = $pdo->prepare("SELECT * FROM voicely_contacts WHERE status = ? ORDER BY id DESC");
            $stmt->execute([$filter]);
        } else {
            $stmt = $pdo->query("SELECT * FROM voicely_contacts ORDER BY id DESC");
        }
        $leads = $stmt->fetchAll();

        // Calculate stats
        $statStmt = $pdo->query("SELECT status, COUNT(*) as count FROM voicely_contacts GROUP BY status");
        while ($row = $statStmt->fetch()) {
            $st = $row['status'] ?: 'new';
            if (isset($stats[$st])) {
                $stats[$st] = intval($row['count']);
            }
            $stats['total'] += intval($row['count']);
        }
    } catch (Exception $e) {
        $msg = "Database query error: " . $e->getMessage();
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Voicely CRM — Leads & Inquiries</title>
  <link rel="icon" type="image/png" href="/favicon.png">
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card: #111827;
      --card-hover: #1f2937;
      --border: #1f2937;
      --emerald: #10b981;
      --emerald-dark: #059669;
      --text: #f9fafb;
      --muted: #9ca3af;
      --accent: #6366f1;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Geist', sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; }
    
    /* Header */
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon { width: 40px; height: 40px; border-radius: 10px; background: linear-gradient(135deg, #10b981, #047857); display: flex; align-items: center; justify-content: center; font-weight: 700; color: white; font-size: 18px; }
    .brand-title { font-size: 20px; font-weight: 700; }
    .brand-subtitle { font-size: 12px; color: var(--muted); }
    .header-actions { display: flex; gap: 10px; align-items: center; }
    .btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; text-decoration: none; border: none; transition: all 0.2s; }
    .btn-primary { background: var(--emerald); color: #042f2e; }
    .btn-primary:hover { background: #34d399; }
    .btn-secondary { background: var(--border); color: var(--text); }
    .btn-secondary:hover { background: var(--card-hover); }
    .btn-wa { background: #25D366; color: #07381a; }
    .btn-wa:hover { background: #3fe07b; }
    
    /* Login Form */
    .login-box { max-width: 400px; margin: 80px auto; background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 32px; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
    .input { width: 100%; padding: 12px 16px; background: #1a2234; border: 1px solid var(--border); border-radius: 8px; color: white; font-size: 14px; margin-bottom: 16px; outline: none; }
    .input:focus { border-color: var(--emerald); }
    
    /* Stats Bar */
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px; }
    .stat-val { font-size: 28px; font-weight: 700; color: var(--emerald); }
    .stat-lbl { font-size: 13px; color: var(--muted); margin-top: 4px; }
    
    /* Filter Bar */
    .filter-bar { display: flex; gap: 8px; margin-bottom: 20px; overflow-x: auto; padding-bottom: 4px; }
    .filter-pill { padding: 6px 14px; border-radius: 20px; font-size: 12px; text-decoration: none; color: var(--muted); background: var(--card); border: 1px solid var(--border); transition: all 0.2s; }
    .filter-pill.active { background: var(--emerald); color: #042f2e; font-weight: 600; border-color: var(--emerald); }
    
    /* Table & Cards */
    .leads-table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
    .leads-table th { background: #151d2f; padding: 14px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.05em; }
    .leads-table td { padding: 14px 16px; border-top: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
    .leads-table tr:hover { background: #162032; }
    
    .badge { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
    .badge-new { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }
    .badge-contacted { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-qualified { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
    .badge-closed { background: rgba(107, 114, 128, 0.2); color: #9ca3af; border: 1px solid rgba(107, 114, 128, 0.4); }
    
    .alert { padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; background: rgba(16, 185, 129, 0.15); border: 1px solid var(--emerald); color: #34d399; }
  </style>
</head>
<body>

<div class="container">
  <div class="header">
    <div class="brand">
      <div class="brand-icon">Vy</div>
      <div>
        <div class="brand-title">Voicely CRM Leads Portal</div>
        <div class="brand-subtitle">Client Showroom & Online Inquiries · Maruthi Furnitures & Mattresses</div>
      </div>
    </div>
    <?php if ($authenticated): ?>
      <div class="header-actions">
        <a href="export_leads.php?token=VoicelyExport2026!" class="btn btn-secondary">📥 Export CSV</a>
        <a href="backup_db.php?token=VoicelyBackup2026!" class="btn btn-secondary">💾 Backup DB</a>
        <a href="leads_admin.php?action=logout" class="btn btn-secondary">Sign Out</a>
      </div>
    <?php endif; ?>
  </div>

  <?php if (!$authenticated): ?>
    <div class="login-box">
      <h2 style="font-size: 18px; margin-bottom: 16px;">🔐 Security Verification</h2>
      <p style="font-size: 13px; color: var(--muted); margin-bottom: 20px;">Enter your admin passkey or token to access the CRM console.</p>
      <form method="POST" action="leads_admin.php">
        <input type="password" name="password" placeholder="Voicely Admin Key" class="input" required autofocus>
        <button type="submit" class="btn btn-primary" style="width: 100%; justify-content: center;">Access Dashboard</button>
      </form>
    </div>
  <?php else: ?>

    <?php if ($msg): ?>
      <div class="alert"><?php echo htmlspecialchars($msg); ?></div>
    <?php endif; ?>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-val"><?php echo $stats['total']; ?></div>
        <div class="stat-lbl">Total Leads Received</div>
      </div>
      <div class="stat-card">
        <div class="stat-val" style="color: #60a5fa;"><?php echo $stats['new']; ?></div>
        <div class="stat-lbl">Awaiting Response</div>
      </div>
      <div class="stat-card">
        <div class="stat-val" style="color: #fbbf24;"><?php echo $stats['contacted']; ?></div>
        <div class="stat-lbl">Contacted / In Progress</div>
      </div>
      <div class="stat-card">
        <div class="stat-val"><?php echo $stats['qualified']; ?></div>
        <div class="stat-lbl">Showroom Visits Scheduled</div>
      </div>
    </div>

    <div class="filter-bar">
      <a href="leads_admin.php?filter=all" class="filter-pill <?php echo (!isset($_GET['filter']) || $_GET['filter']=='all') ? 'active' : ''; ?>">All Leads (<?php echo $stats['total']; ?>)</a>
      <a href="leads_admin.php?filter=new" class="filter-pill <?php echo (isset($_GET['filter']) && $_GET['filter']=='new') ? 'active' : ''; ?>">New (<?php echo $stats['new']; ?>)</a>
      <a href="leads_admin.php?filter=contacted" class="filter-pill <?php echo (isset($_GET['filter']) && $_GET['filter']=='contacted') ? 'active' : ''; ?>">Contacted (<?php echo $stats['contacted']; ?>)</a>
      <a href="leads_admin.php?filter=qualified" class="filter-pill <?php echo (isset($_GET['filter']) && $_GET['filter']=='qualified') ? 'active' : ''; ?>">Showroom Booked (<?php echo $stats['qualified']; ?>)</a>
      <a href="leads_admin.php?filter=closed" class="filter-pill <?php echo (isset($_GET['filter']) && $_GET['filter']=='closed') ? 'active' : ''; ?>">Closed</a>
    </div>

    <table class="leads-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Lead Name</th>
          <th>Contact Info</th>
          <th>Subject / Requirement</th>
          <th>Received At</th>
          <th>Status</th>
          <th>Quick Actions</th>
        </tr>
      </thead>
      <tbody>
        <?php if (empty($leads)): ?>
          <tr>
            <td colspan="7" style="text-align: center; padding: 40px; color: var(--muted);">No leads found in this view.</td>
          </tr>
        <?php else: ?>
          <?php foreach ($leads as $l): ?>
            <?php 
              $phone_clean = preg_replace('/[^0-9]/', '', $l['phone'] ?? '');
              if (strlen($phone_clean) == 10) $phone_clean = '91' . $phone_clean;
              $wa_text = urlencode("Namaste " . ($l['name'] ?? 'Sir') . "! Thank you for contacting Maruthi Furnitures & Mattresses, Siddipet. We received your inquiry regarding our Teak cots & Eurotop mattresses. When would you like to visit our showroom?");
            ?>
            <tr>
              <td>#<?php echo $l['id']; ?></td>
              <td><strong><?php echo htmlspecialchars($l['name']); ?></strong></td>
              <td>
                <div>📞 <a href="tel:<?php echo htmlspecialchars($l['phone']); ?>" style="color: var(--emerald); text-decoration: none;"><?php echo htmlspecialchars($l['phone'] ?: 'N/A'); ?></a></div>
                <div style="font-size: 11px; color: var(--muted);">✉️ <?php echo htmlspecialchars($l['email'] ?: 'N/A'); ?></div>
              </td>
              <td>
                <div style="font-weight: 500;"><?php echo htmlspecialchars($l['subject'] ?: 'Website Lead'); ?></div>
                <div style="font-size: 12px; color: var(--muted); max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"><?php echo htmlspecialchars($l['message'] ?: ''); ?></div>
              </td>
              <td style="color: var(--muted); font-size: 12px;"><?php echo htmlspecialchars($l['created_at']); ?></td>
              <td>
                <span class="badge badge-<?php echo strtolower($l['status'] ?: 'new'); ?>"><?php echo strtoupper($l['status'] ?: 'NEW'); ?></span>
                <form method="POST" action="leads_admin.php" style="margin-top: 6px;">
                  <input type="hidden" name="contact_id" value="<?php echo $l['id']; ?>">
                  <input type="hidden" name="update_status" value="1">
                  <select name="status" onchange="this.form.submit()" style="background: #1a2234; color: white; border: 1px solid var(--border); border-radius: 4px; padding: 2px 6px; font-size: 11px;">
                    <option value="new" <?php echo ($l['status']=='new' || !$l['status'])?'selected':''; ?>>New</option>
                    <option value="contacted" <?php echo ($l['status']=='contacted')?'selected':''; ?>>Contacted</option>
                    <option value="qualified" <?php echo ($l['status']=='qualified')?'selected':''; ?>>Qualified</option>
                    <option value="closed" <?php echo ($l['status']=='closed')?'selected':''; ?>>Closed</option>
                  </select>
                </form>
              </td>
              <td>
                <div style="display: flex; gap: 6px;">
                  <?php if (!empty($phone_clean)): ?>
                    <a href="https://wa.me/<?php echo $phone_clean; ?>?text=<?php echo $wa_text; ?>" target="_blank" class="btn btn-wa" style="padding: 4px 10px; font-size: 11px;" title="Chat on WhatsApp">💬 WhatsApp</a>
                    <a href="tel:<?php echo $phone_clean; ?>" class="btn btn-secondary" style="padding: 4px 10px; font-size: 11px;" title="Direct Call">📞 Call</a>
                  <?php endif; ?>
                </div>
              </td>
            </tr>
          <?php endforeach; ?>
        <?php endif; ?>
      </tbody>
    </table>

  <?php endif; ?>
</div>

</body>
</html>
