SUSPICIOUS_KEYWORDS = [
    "wget", "curl", "chmod +x", "authorized_keys", "crontab", 
    "/tmp", "nc ", "bash -i", "history -c", "rm -rf", "base64", 
    "xmr", "miner"
]

FEATURE_COLUMNS = [
    'duration_sec', 'protocol', 'has_client_version',
    'n_login_failed', 'n_login_success', 'login_success_ratio',
    'n_unique_usernames', 'n_unique_passwords', 'avg_secs_between_logins',
    'n_commands', 'n_unique_commands', 'n_failed_commands',
    'avg_secs_between_commands', 'avg_command_length',
    'n_suspicious_commands', 'n_download_attempts', 'n_file_uploads',
    'no_login_attempted', 'session_incomplete',
    'ip_sessions_last_60s', 'ip_sessions_last_300s',
    'ip_failed_logins_last_300s', 'ip_distinct_usernames_last_300s'
]

LABELS = ['normal', 'recon', 'brute_force', 'command_attack']

THREAT_LEVEL = {
    'normal': 'Low',
    'recon': 'Medium',
    'brute_force': 'High',
    'command_attack': 'Critical'
}
