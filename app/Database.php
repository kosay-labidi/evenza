<?php
declare(strict_types=1);
namespace Evenza;
use PDO;
final class Database {
    private static ?PDO $connection = null;
    public static function get(): PDO {
        if (!self::$connection) {
            $host = getenv('DB_HOST') ?: '127.0.0.1';
            $port = getenv('DB_PORT') ?: '3306';
            $name = getenv('DB_DATABASE') ?: 'evenza';
            if (!preg_match('/^[a-zA-Z0-9_]+$/', $name)) throw new \RuntimeException('Nom de base invalide.');
            self::$connection = new PDO("mysql:host=$host;port=$port;dbname=$name;charset=utf8mb4", getenv('DB_USERNAME') ?: 'evenza', getenv('DB_PASSWORD') ?: '', [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC, PDO::ATTR_EMULATE_PREPARES=>false]);
            self::$connection->exec("SET time_zone = '+01:00'");
        }
        return self::$connection;
    }
}
