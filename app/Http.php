<?php
declare(strict_types=1);
namespace Evenza;
final class Http {
    public static function json(array $data, int $status = 200): never {
        http_response_code($status); header('Content-Type: application/json; charset=utf-8'); header('Cache-Control: no-store');
        echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR); exit;
    }
    public static function fail(string $message, int $status=422, array $errors=[]): never { self::json(['message'=>$message,'errors'=>$errors],$status); }
    public static function body(): array {
        if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 1048576) self::fail('Requête trop volumineuse.',413);
        try { $body=json_decode(file_get_contents('php://input'),true,32,JSON_THROW_ON_ERROR); }
        catch (\JsonException) { self::fail('Corps JSON invalide.'); }
        if (!is_array($body)) self::fail('Objet JSON attendu.');
        return $body;
    }
    public static function csrf(): void {
        if (!hash_equals($_SESSION['csrf'] ?? '', $_SERVER['HTTP_X_CSRF_TOKEN'] ?? 'missing')) self::fail('Session expirée. Rechargez la page.',419);
    }
}
