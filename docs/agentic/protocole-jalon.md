# Protocole de jalon

La procédure fait foi à deux endroits ; ce fichier ne la recopie pas.

- **SPEC §17.3** : étapes 0 à 8 (préparer, cadrer, planifier, découper, implémenter, gate, revues indépendantes, vérifier, clore).
- **`.claude/skills/milestone/SKILL.md`** : le skill `milestone`, invoqué quand l'opérateur dit « lance le jalon Mx ».

Rappels pour l'opérateur :

- Un jalon = une session ; `/clear` entre deux jalons. L'orchestrateur n'enchaîne jamais sur le jalon suivant.
- Branche `jalon/mX`, commits par lot cohérent, ni push ni merge sans demande.
- Plugins activés selon `.claude/rules/skills-par-jalon.md` ; `/reload-plugins` demandé en début de jalon.
- À la clôture : `docs/security/threat-model.md` et `docs/invariants.md` mis à jour, coût noté dans `couts.md`, puis `/graphify` (à partir de M1) lancé par l'opérateur.

Modèles et agents : SPEC §17.2. Discipline de tokens : SPEC §17.4.
