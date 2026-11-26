<?php
declare(strict_types=1);
define('ROOT', dirname(__DIR__));
spl_autoload_register(function (string $class): void {
    $file = ROOT . '/app/' . str_replace('Evenza\\', '', $class) . '.php';
    if (is_file($file)) require $file;
});
if (is_file(ROOT . '/.env')) {
    foreach (file(ROOT . '/.env', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        if (str_starts_with(trim($line), '#') || !str_contains($line, '=')) continue;
        [$key, $value] = explode('=', $line, 2);
        if (getenv(trim($key)) === false) putenv(trim($key) . '=' . trim($value, " \t\n\r\0\x0B\"'"));
    }
}
date_default_timezone_set('Africa/Tunis');
ini_set('display_errors', '0');
ini_set('log_errors', '1');
ini_set('error_log', ROOT . '/storage/php.log');
if (PHP_SAPI !== 'cli') {
    session_name('evenza_session');
    session_set_cookie_params(['lifetime'=>0, 'path'=>'/', 'secure'=>getenv('SESSION_SECURE') === 'true', 'httponly'=>true, 'samesite'=>'Lax']);
    ini_set('session.use_strict_mode', '1');
    session_start();
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: DENY');
    header('Referrer-Policy: same-origin');
    header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'");
}
