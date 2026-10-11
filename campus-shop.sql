-- =====================================================================
--  Campus Shop : base de données (PostgreSQL 13+)
--  Lancer :  createdb campus_shop && psql -d campus_shop -f base.sql
--  Montants en Ariary : NUMERIC(12,0) (pas de centimes)
-- =====================================================================

DROP TABLE IF EXISTS reconnaissance_dette, echeance, paiement, vente, produit, client CASCADE;

-- ---------------------------------------------------------------------
--  CLIENT : tous les clients (nom seulement)
-- ---------------------------------------------------------------------
CREATE TABLE client (
    id_client  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom        VARCHAR(120) NOT NULL
);

-- ---------------------------------------------------------------------
--  PRODUIT : la facilité de paiement est initialisée par l'admin
-- ---------------------------------------------------------------------
CREATE TABLE produit (
    id_produit        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom               VARCHAR(150) NOT NULL,
    prix_achat        NUMERIC(12,0) NOT NULL CHECK (prix_achat >= 0),
    prix_vente        NUMERIC(12,0) NOT NULL CHECK (prix_vente >= 0),
    stock             INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    photo             TEXT,                               -- chemin ou URL de l'image
    facilite_paiement BOOLEAN NOT NULL DEFAULT FALSE,
    nb_tranches       SMALLINT CHECK (nb_tranches BETWEEN 2 AND 6),
    intervalle_jours  SMALLINT CHECK (intervalle_jours IN (7, 14, 30)),
    created_at        TIMESTAMP NOT NULL DEFAULT now(),
    -- tranches et intervalle obligatoires si facilité, interdits sinon
    CONSTRAINT ck_facilite CHECK (
        (facilite_paiement AND nb_tranches IS NOT NULL AND intervalle_jours IS NOT NULL)
     OR (NOT facilite_paiement AND nb_tranches IS NULL AND intervalle_jours IS NULL))
);

-- ---------------------------------------------------------------------
--  VENTE : sert aussi de facture (numero_facture)
--  Les prix sont copiés au moment de la vente : un changement de prix
--  ne modifie jamais les anciens gains.
-- ---------------------------------------------------------------------
CREATE TABLE vente (
    id_vente             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numero_facture       INTEGER GENERATED ALWAYS AS IDENTITY UNIQUE,
    id_client            INTEGER NOT NULL REFERENCES client(id_client),
    id_produit           INTEGER NOT NULL REFERENCES produit(id_produit),
    date_vente           DATE NOT NULL DEFAULT CURRENT_DATE,
    quantite             INTEGER NOT NULL CHECK (quantite > 0),
    prix_achat_unitaire  NUMERIC(12,0) NOT NULL CHECK (prix_achat_unitaire >= 0),
    prix_vente_unitaire  NUMERIC(12,0) NOT NULL CHECK (prix_vente_unitaire >= 0),
    avec_facilite        BOOLEAN NOT NULL DEFAULT FALSE,   -- par défaut : sans facilité
    acompte              NUMERIC(12,0) NOT NULL DEFAULT 0 CHECK (acompte >= 0),
    CONSTRAINT ck_acompte CHECK (acompte <= quantite * prix_vente_unitaire)
);
CREATE INDEX ix_vente_date    ON vente(date_vente);
CREATE INDEX ix_vente_client  ON vente(id_client);
CREATE INDEX ix_vente_produit ON vente(id_produit);

-- ---------------------------------------------------------------------
--  PAIEMENT : chaque versement (l'acompte est le premier)
-- ---------------------------------------------------------------------
CREATE TABLE paiement (
    id_paiement    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_vente       INTEGER NOT NULL REFERENCES vente(id_vente) ON DELETE CASCADE,
    date_paiement  DATE NOT NULL DEFAULT CURRENT_DATE,
    montant        NUMERIC(12,0) NOT NULL CHECK (montant > 0)
);
CREATE INDEX ix_paiement_vente ON paiement(id_vente);

-- ---------------------------------------------------------------------
--  ECHEANCE : échéancier d'une vente avec facilité
-- ---------------------------------------------------------------------
CREATE TABLE echeance (
    id_vente        INTEGER NOT NULL REFERENCES vente(id_vente) ON DELETE CASCADE,
    numero_tranche  SMALLINT NOT NULL CHECK (numero_tranche > 0),
    date_echeance   DATE NOT NULL,
    montant_prevu   NUMERIC(12,0) NOT NULL CHECK (montant_prevu > 0),
    PRIMARY KEY (id_vente, numero_tranche)
);

-- ---------------------------------------------------------------------
--  RECONNAISSANCE_DE_DETTE : uniquement pour les ventes avec facilité
--  (au plus une par vente)
-- ---------------------------------------------------------------------
CREATE TABLE reconnaissance_dette (
    id_reconnaissance  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_vente           INTEGER NOT NULL UNIQUE REFERENCES vente(id_vente) ON DELETE CASCADE,
    numero_etu         CHAR(4) NOT NULL CHECK (numero_etu ~ '^[0-9]{4}$'),
    photo_client       TEXT NOT NULL,                      -- chemin ou URL de l'image
    telephone          VARCHAR(20) NOT NULL,
    a_whatsapp         BOOLEAN NOT NULL DEFAULT TRUE,      -- avec / sans WhatsApp
    signature          TEXT NOT NULL,                      -- image de la signature
    date_signature     DATE NOT NULL DEFAULT CURRENT_DATE,
    montant_reconnu    NUMERIC(12,0) NOT NULL CHECK (montant_reconnu > 0)  -- total - acompte
);

-- =====================================================================
--  TRIGGERS : règles métier
-- =====================================================================

-- Vente : vérifie la facilité autorisée, vérifie et décrémente le stock
CREATE OR REPLACE FUNCTION trg_vente_avant_insert() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.avec_facilite AND NOT (SELECT facilite_paiement FROM produit WHERE id_produit = NEW.id_produit) THEN
        RAISE EXCEPTION 'Facilité de paiement non autorisée pour ce produit';
    END IF;
    IF NOT NEW.avec_facilite THEN
        NEW.acompte := NEW.quantite * NEW.prix_vente_unitaire;   -- comptant
    END IF;
    UPDATE produit SET stock = stock - NEW.quantite
     WHERE id_produit = NEW.id_produit AND stock >= NEW.quantite;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Stock insuffisant';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER vente_avant_insert BEFORE INSERT ON vente
    FOR EACH ROW EXECUTE FUNCTION trg_vente_avant_insert();

-- Paiement : interdit de payer plus que le total de la vente
CREATE OR REPLACE FUNCTION trg_paiement_avant_insert() RETURNS TRIGGER AS $$
DECLARE v_total NUMERIC; v_paye NUMERIC;
BEGIN
    SELECT quantite * prix_vente_unitaire INTO v_total FROM vente WHERE id_vente = NEW.id_vente;
    SELECT COALESCE(SUM(montant), 0) INTO v_paye FROM paiement WHERE id_vente = NEW.id_vente;
    IF v_paye + NEW.montant > v_total THEN
        RAISE EXCEPTION 'Le paiement dépasse le reste à payer';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER paiement_avant_insert BEFORE INSERT ON paiement
    FOR EACH ROW EXECUTE FUNCTION trg_paiement_avant_insert();

-- Reconnaissance : seulement pour une vente avec facilité
CREATE OR REPLACE FUNCTION trg_reconnaissance_avant_insert() RETURNS TRIGGER AS $$
BEGIN
    IF NOT (SELECT avec_facilite FROM vente WHERE id_vente = NEW.id_vente) THEN
        RAISE EXCEPTION 'Une reconnaissance de dette n''existe que pour une vente avec facilité';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER reconnaissance_avant_insert BEFORE INSERT ON reconnaissance_dette
    FOR EACH ROW EXECUTE FUNCTION trg_reconnaissance_avant_insert();

-- Génère l'échéancier : (total - acompte) réparti en nb_tranches,
-- une tranche tous les intervalle_jours, le reliquat sur la dernière.
CREATE OR REPLACE FUNCTION generer_echeances(p_vente INTEGER) RETURNS VOID AS $$
DECLARE v RECORD; r_reste NUMERIC; r_base NUMERIC; k INTEGER;
BEGIN
    SELECT ve.date_vente, ve.acompte, ve.quantite * ve.prix_vente_unitaire AS total,
           p.nb_tranches, p.intervalle_jours
      INTO v
      FROM vente ve JOIN produit p USING (id_produit)
     WHERE ve.id_vente = p_vente AND ve.avec_facilite;
    IF NOT FOUND THEN RETURN; END IF;

    r_reste := v.total - v.acompte;
    IF r_reste <= 0 THEN RETURN; END IF;
    r_base := FLOOR(r_reste / v.nb_tranches);

    DELETE FROM echeance WHERE id_vente = p_vente;
    FOR k IN 1..v.nb_tranches LOOP
        INSERT INTO echeance (id_vente, numero_tranche, date_echeance, montant_prevu)
        VALUES (p_vente, k, v.date_vente + k * v.intervalle_jours,
                CASE WHEN k = v.nb_tranches THEN r_reste - r_base * (v.nb_tranches - 1) ELSE r_base END);
    END LOOP;
END; $$ LANGUAGE plpgsql;

-- =====================================================================
--  VUES : calculs du back office
-- =====================================================================

-- Détail de chaque vente : total, gain, payé, reste, retard
CREATE OR REPLACE VIEW v_vente AS
SELECT v.id_vente, v.numero_facture, v.date_vente,
       c.nom AS client, p.nom AS produit, v.quantite, v.avec_facilite,
       v.quantite * v.prix_vente_unitaire                         AS total,
       v.quantite * (v.prix_vente_unitaire - v.prix_achat_unitaire) AS gain,
       COALESCE(pa.total_paye, 0)                                 AS total_paye,
       v.quantite * v.prix_vente_unitaire - COALESCE(pa.total_paye, 0) AS reste,
       (v.quantite * v.prix_vente_unitaire - COALESCE(pa.total_paye, 0) > 0
        AND COALESCE(pa.total_paye, 0) <
            v.acompte + COALESCE((SELECT SUM(e.montant_prevu) FROM echeance e
                                   WHERE e.id_vente = v.id_vente
                                     AND e.date_echeance <= CURRENT_DATE), 0)) AS en_retard
  FROM vente v
  JOIN client  c ON c.id_client  = v.id_client
  JOIN produit p ON p.id_produit = v.id_produit
  LEFT JOIN (SELECT id_vente, SUM(montant) AS total_paye FROM paiement GROUP BY id_vente) pa
         ON pa.id_vente = v.id_vente;

-- Chiffre d'affaires et gains par jour
CREATE OR REPLACE VIEW v_gains_jour AS
SELECT date_vente AS jour, SUM(total) AS chiffre_affaires, SUM(gain) AS gain
  FROM v_vente GROUP BY date_vente ORDER BY date_vente;

-- Dettes en cours
CREATE OR REPLACE VIEW v_dettes AS
SELECT v.*, r.numero_etu, r.telephone, r.a_whatsapp
  FROM v_vente v
  LEFT JOIN reconnaissance_dette r ON r.id_vente = v.id_vente
 WHERE v.reste > 0;

-- =====================================================================
--  REQUETES UTILES (à adapter)
-- =====================================================================
-- Gains sur un intervalle, par jour :
--   SELECT jour, gain FROM v_gains_jour WHERE jour BETWEEN '2026-10-01' AND '2026-10-10';
-- Gains sur un intervalle, par semaine :
--   SELECT date_trunc('week', date_vente)::date AS semaine, SUM(gain) AS gain
--     FROM v_vente WHERE date_vente BETWEEN '2026-10-01' AND '2026-10-10' GROUP BY 1 ORDER BY 1;
-- Courbe de croissance (CA cumulé) :
--   SELECT jour, SUM(chiffre_affaires) OVER (ORDER BY jour) AS ca_cumule FROM v_gains_jour;
-- Clients en retard :
--   SELECT client, produit, reste, telephone, a_whatsapp FROM v_dettes WHERE en_retard;

-- =====================================================================
--  DONNEES D'EXEMPLE (supprime cette partie pour une base vide)
-- =====================================================================
INSERT INTO produit (nom, prix_achat, prix_vente, stock, facilite_paiement, nb_tranches, intervalle_jours) VALUES
 ('Clé USB 32 Go',        18000, 25000,  60, TRUE,  2, 14),
 ('Powerbank 10 000 mAh', 45000, 60000,  30, TRUE,  3, 14),
 ('Cahier 200 pages',      2000,  3000, 200, FALSE, NULL, NULL);

INSERT INTO client (nom) VALUES ('Aina'), ('Hery');

-- Vente 1 : sans facilité (comptant)
INSERT INTO vente (id_client, id_produit, quantite, prix_achat_unitaire, prix_vente_unitaire)
SELECT (SELECT id_client FROM client WHERE nom = 'Aina'), id_produit, 3, prix_achat, prix_vente
  FROM produit WHERE nom = 'Cahier 200 pages';
INSERT INTO paiement (id_vente, montant)
SELECT id_vente, quantite * prix_vente_unitaire FROM vente WHERE numero_facture = 1;

-- Vente 2 : avec facilité (acompte de 30 000 sur 60 000)
INSERT INTO vente (id_client, id_produit, quantite, prix_achat_unitaire, prix_vente_unitaire, avec_facilite, acompte)
SELECT (SELECT id_client FROM client WHERE nom = 'Hery'), id_produit, 1, prix_achat, prix_vente, TRUE, 30000
  FROM produit WHERE nom = 'Powerbank 10 000 mAh';
INSERT INTO paiement (id_vente, montant) SELECT id_vente, acompte FROM vente WHERE numero_facture = 2;
SELECT generer_echeances(id_vente) FROM vente WHERE numero_facture = 2;
INSERT INTO reconnaissance_dette (id_vente, numero_etu, photo_client, telephone, a_whatsapp, signature, montant_reconnu)
SELECT id_vente, '1234', 'photos/hery.jpg', '034 00 000 00', TRUE, 'signatures/hery.png',
       quantite * prix_vente_unitaire - acompte
  FROM vente WHERE numero_facture = 2;