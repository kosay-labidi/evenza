<?php
declare(strict_types=1);
namespace Evenza;
final class Auth {
    public static function user(): array {
        if (!isset($_SESSION['uid'])) Http::fail('Connectez-vous pour continuer.',401);
        if (time() - ($_SESSION['last_activity'] ?? 0) > 7200) { $_SESSION=[]; Http::fail('Votre session a expiré.',401); }
        $q=Database::get()->prepare('SELECT id,name,email,role,phone,active,availability,skills FROM users WHERE id=?');
        $q->execute([$_SESSION['uid']]); $u=$q->fetch();
        if (!$u || !$u['active']) { $_SESSION=[]; Http::fail('Compte indisponible.',401); }
        $_SESSION['last_activity']=time(); return $u;
    }
    public static function login(array $b): never {
        $db=Database::get(); $email=strtolower(trim((string)($b['email']??''))); $ip=$_SERVER['REMOTE_ADDR']??'unknown';
        $q=$db->prepare('SELECT COUNT(*) FROM login_attempts WHERE (email=? OR ip=?) AND success=0 AND created_at > DATE_SUB(NOW(), INTERVAL 15 MINUTE)');
        $q->execute([$email,$ip]); if ((int)$q->fetchColumn()>=10) Http::fail('Trop de tentatives. Réessayez dans 15 minutes.',429);
        $q=$db->prepare('SELECT * FROM users WHERE email=?'); $q->execute([$email]); $u=$q->fetch();
        $valid=password_verify((string)($b['password']??''),$u['password_hash']??'$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2uheWG/igi');
        $ok=$u && $u['active'] && $valid;
        $db->prepare('INSERT INTO login_attempts(email,ip,success) VALUES(?,?,?)')->execute([substr($email,0,190),$ip,(int)$ok]);
        if (!$ok) Http::fail('Adresse e-mail ou mot de passe incorrect.',401);
        session_regenerate_id(true); $_SESSION=['uid'=>$u['id'],'csrf'=>bin2hex(random_bytes(32)),'last_activity'=>time()];
        Http::json(['user'=>self::user(),'csrf'=>$_SESSION['csrf']]);
    }
    public static function register(array $b): never {
        $name=trim((string)($b['name']??'')); $email=strtolower(trim((string)($b['email']??''))); $pw=(string)($b['password']??'');
        if (!$name || strlen($name)>120 || !filter_var($email,FILTER_VALIDATE_EMAIL) || strlen($email)>190 || strlen($pw)<12 || strlen($pw)>200) Http::fail('Nom, e-mail valide et mot de passe de 12 à 200 caractères requis.');
        $db=Database::get();
        $db->prepare('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)')->execute([$name,$email,password_hash($pw,PASSWORD_DEFAULT),'Participant']);
        Http::json(['message'=>'Compte créé. Vous pouvez vous connecter.'],201);
    }
    /** Portée SQL des données : y compris pour les listes de relations et les détails. */
    public static function scope(string $entity,array $u,string $alias='t'): array {
        $id=(int)$u['id']; $role=$u['role'];
        if ($role==='Administrateur') return ['1=1',[]];
        $event="SELECT id FROM events WHERE organizer_id=$id";
        if ($role==='Organisateur') return match($entity) {
            'users'=>["$alias.id=?",[$id]],
            'events'=>["$alias.organizer_id=?",[$id]],
            'programs','participants','reservations','allocations','suggestions'=>["$alias.event_id IN ($event)",[]],
            'complaints'=>["$alias.participant_id IN (SELECT id FROM participants WHERE event_id IN ($event))",[]],
            default=>['1=1',[]]
        };
        if ($role==='Prestataire') return match($entity) {
            'users'=>["$alias.id=?",[$id]], 'providers'=>["$alias.user_id=?",[$id]],
            'services'=>["$alias.provider_id IN (SELECT id FROM providers WHERE user_id=?)",[$id]],
            'reservations'=>["$alias.service_id IN (SELECT s.id FROM services s JOIN providers p ON p.id=s.provider_id WHERE p.user_id=?)",[$id]],
            'events'=>["$alias.id IN (SELECT r.event_id FROM reservations r JOIN services s ON s.id=r.service_id JOIN providers p ON p.id=s.provider_id WHERE p.user_id=?)",[$id]],
            'programs'=>["$alias.event_id IN (SELECT r.event_id FROM reservations r JOIN services s ON s.id=r.service_id JOIN providers p ON p.id=s.provider_id WHERE p.user_id=?)",[$id]],
            default=>['1=0',[]]
        };
        if ($role==='Client') return match($entity) {
            'events'=>["$alias.client_id=?",[$id]], 'programs'=>["$alias.event_id IN (SELECT id FROM events WHERE client_id=?)",[$id]],
            'users'=>["$alias.id=?",[$id]],default=>['1=0',[]]
        };
        return match($entity) {
            'events'=>["($alias.status='Confirmé' OR $alias.id IN (SELECT event_id FROM participants WHERE user_id=?))",[$id]],
            'programs'=>["$alias.event_id IN (SELECT id FROM events WHERE status='Confirmé') OR $alias.event_id IN (SELECT event_id FROM participants WHERE user_id=?)",[$id]],
            'participants'=>["$alias.user_id=?",[$id]],'users'=>["$alias.id=?",[$id]],
            'complaints'=>["$alias.participant_id IN (SELECT id FROM participants WHERE user_id=?)",[$id]],default=>['1=0',[]]
        };
    }
    public static function canWrite(string $e,array $u,string $method): bool {
        if ($u['role']==='Administrateur') return true;
        if ($u['role']==='Organisateur') return in_array($e,['events','programs','participants','resources','allocations','reservations','suggestions','complaints'],true);
        if ($u['role']==='Prestataire') return in_array($e,['services','providers','reservations'],true) && !($e!=='services' && $method!=='PUT');
        if ($u['role']==='Client') return $e==='events' && $method!=='DELETE';
        return in_array($e,['participants','complaints'],true) && $method!=='DELETE';
    }
}
