<?php
declare(strict_types=1);
namespace Evenza;
/** Métadonnées partagées par les formulaires et les validations. Aucun nom SQL ne vient du navigateur. */
final class Modules {
    public static function all(): array {
        $f = fn(string $label, string $type='text', bool $required=true, array $extra=[]) => ['label'=>$label,'type'=>$type,'required'=>$required]+$extra;
        $choice = fn(string $label, array $options) => $f($label,'select',true,['options'=>$options]);
        $ref = fn(string $label, string $entity, bool $required=true, ?string $role=null) => $f($label,'relation',$required,['entity'=>$entity,'role'=>$role]);
        return [
            'events'=>['label'=>'Événements','group'=>'events','singular'=>'événement','fields'=>[
                'title'=>$f('Nom de l’événement'), 'description'=>$f('Description','textarea',false),
                'start_at'=>$f('Début','datetime-local'), 'end_at'=>$f('Fin','datetime-local'), 'location'=>$f('Lieu'),
                'type'=>$choice('Type',['Mariage','Entreprise','Privé','Conférence','Autre']),
                'capacity'=>$f('Capacité','number',true,['min'=>1]), 'budget'=>$f('Budget (TND)','number',true,['min'=>0,'step'=>'0.01']),
                'status'=>$choice('Statut',['Brouillon','En préparation','Confirmé','Terminé','Annulé']),
                'client_id'=>$ref('Client','users',false,'Client'), 'organizer_id'=>$ref('Organisateur','users',false,'Organisateur')]],
            'users'=>['label'=>'Utilisateurs','group'=>'users','singular'=>'utilisateur','fields'=>[
                'name'=>$f('Nom complet'), 'email'=>$f('Adresse e-mail','email'), 'password'=>$f('Mot de passe','password',false),
                'role'=>$choice('Rôle',['Administrateur','Organisateur','Client','Prestataire','Participant']),
                'phone'=>$f('Téléphone','tel',false), 'active'=>$choice('Compte actif',['1','0']),
                'availability'=>$f('Disponibilités','text',false),'skills'=>$f('Compétences','text',false)]],
            'providers'=>['label'=>'Prestataires','group'=>'providers','singular'=>'prestataire','fields'=>[
                'name'=>$f('Raison sociale'),'specialty'=>$f('Spécialité'),'city'=>$f('Ville'),'email'=>$f('E-mail','email'),
                'phone'=>$f('Téléphone','tel',false),'user_id'=>$ref('Compte prestataire','users',false,'Prestataire'),
                'availability'=>$f('Disponibilités','text',false),'status'=>$choice('Statut',['Disponible','Réservé','Inactif'])]],
            'services'=>['label'=>'Services','group'=>'providers','singular'=>'service','fields'=>[
                'provider_id'=>$ref('Prestataire','providers'),'name'=>$f('Nom du service'),'description'=>$f('Description','textarea',false),
                'price'=>$f('Tarif (TND)','number',true,['min'=>0,'step'=>'0.01']),'status'=>$choice('Statut',['Actif','Inactif'])]],
            'reservations'=>['label'=>'Réservations','group'=>'providers','singular'=>'réservation','fields'=>[
                'event_id'=>$ref('Événement','events'),'service_id'=>$ref('Service','services'),
                'amount'=>$f('Montant (TND)','number',true,['min'=>0,'step'=>'0.01']),
                'status'=>$choice('Statut',['En attente','Acceptée','Refusée','Annulée']),
                'rating'=>$f('Note sur 5','number',false,['min'=>1,'max'=>5]),'comment'=>$f('Avis','textarea',false)]],
            'programs'=>['label'=>'Programmes','group'=>'programs','singular'=>'session','fields'=>[
                'event_id'=>$ref('Événement','events'),'title'=>$f('Titre de la session'),'description'=>$f('Description','textarea',false),
                'start_at'=>$f('Début','datetime-local'),'end_at'=>$f('Fin','datetime-local'),'speaker'=>$f('Intervenant','text',false),
                'status'=>$choice('Statut',['Planifié','Confirmé','Terminé'])]],
            'participants'=>['label'=>'Participants','group'=>'participants','singular'=>'participant','fields'=>[
                'event_id'=>$ref('Événement','events'),'user_id'=>$ref('Compte participant','users',false,'Participant'),
                'name'=>$f('Nom complet'),'email'=>$f('E-mail','email'),'category'=>$f('Catégorie'),
                'preference'=>$f('Préférence de placement','text',false),'seat'=>$f('Place attribuée','text',false),
                'status'=>$choice('Statut',['Invité','Inscrit','Confirmé','Présent','Absent','Liste d’attente','Annulé','Refusé']),
                'rating'=>$f('Note sur 5','number',false,['min'=>1,'max'=>5]),'feedback'=>$f('Avis','textarea',false)]],
            'complaints'=>['label'=>'Réclamations','group'=>'participants','singular'=>'réclamation','fields'=>[
                'participant_id'=>$ref('Inscription','participants'),'subject'=>$f('Objet'),'message'=>$f('Message','textarea'),
                'status'=>$choice('Statut',['Ouverte','En cours','Résolue']),'response'=>$f('Réponse','textarea',false)]],
            'resources'=>['label'=>'Ressources','group'=>'resources','singular'=>'ressource','fields'=>[
                'name'=>$f('Nom de la ressource'),'category'=>$choice('Catégorie',['Mobilier','Son & lumière','Décoration','Espace','Autre']),
                'quantity'=>$f('Quantité totale','number',true,['min'=>0]),'status'=>$choice('État',['Disponible','Maintenance','Indisponible']),
                'description'=>$f('Description','textarea',false)]],
            'allocations'=>['label'=>'Affectations','group'=>'resources','singular'=>'affectation','fields'=>[
                'event_id'=>$ref('Événement','events'),'resource_id'=>$ref('Ressource','resources'),
                'quantity'=>$f('Quantité','number',true,['min'=>1]),'start_at'=>$f('Début','datetime-local'),'end_at'=>$f('Fin','datetime-local'),
                'status'=>$choice('Statut',['Affecté','Annulé'])]],
            'suggestions'=>['label'=>'Suggestions de programme','group'=>'programs','singular'=>'suggestion','fields'=>[
                'event_id'=>$ref('Événement','events'),'title'=>$f('Titre proposé'),'start_at'=>$f('Début','datetime-local'),
                'end_at'=>$f('Fin','datetime-local'),'status'=>$choice('Statut',['En attente','Validée','Rejetée'])]]
        ];
    }
    public static function get(string $name): array { return self::all()[$name] ?? throw new \InvalidArgumentException('Gestion inconnue.'); }
}
