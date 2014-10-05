from django.db import connection
from calaccess_campaign_browser import models
from calaccess_campaign_browser.management.commands import CalAccessCommand


class Command(CalAccessCommand):
    help = "Load refined and reformatted campaign filers and committees"

    def handle(self, *args, **options):
        self.header("Loading filers and committees")

        # Ignore MySQL "note" warnings so this can be run with DEBUG=True
        self.conn = connection.cursor()
        self.conn.execute("""SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0;""")

        self.drop_temp_tables()
        self.create_temp_tables()
        self.load_candidate_filers()
        self.create_temp_candidate_committee_tables()
        self.load_candidate_committees()
        self.create_temp_pac_tables()
        self.load_pac_filers()
        self.load_pac_committees()
        self.drop_temp_tables()

        # Revert database to default "note" warning behavior
        self.conn.execute("""SET SQL_NOTES=@OLD_SQL_NOTES;""")

    def create_temp_tables(self):
        """
        Create temporary tables we will use as part of this loader.
        """
        self.log(" Creating temporary tables")

        # Create table with unique filers that eliminates
        # dupes and only keeps the one with the highest incremental ID.
        # We do this because we have not determined any logical way to
        # better infer the most complete record.
        sql = """
        CREATE TEMPORARY TABLE tmp_max_filers (
            INDEX(`filer_id`),
            INDEX(`max_id`)
        ) AS (  
            SELECT
                fn.`FILER_ID` as `filer_id`,
                MAX(fn.`id`) as `max_id`
            FROM FILERNAME_CD as fn
            WHERE fn.`FILER_TYPE` = 'CANDIDATE/OFFICEHOLDER'
            OR fn.`FILER_TYPE` = 'RECIPIENT COMMITTEE'
            GROUP BY 1
        );
        """
        self.conn.execute(sql)

        # Create a table with the party affiliation recorded by each filer.
        # This requires brutal removal of duplicates as above.
        sql = """
        CREATE TEMPORARY TABLE tmp_max_filer_party (
            INDEX(`filer_id`),
            INDEX(`party`)
        ) AS (
            SELECT
                ft.`FILER_ID` as `filer_id`,
                ft.`PARTY_CD` as `party`
            FROM FILER_TO_FILER_TYPE_CD as ft
            INNER JOIN (
                SELECT FILER_ID, MAX(`id`) as `id`
                FROM FILER_TO_FILER_TYPE_CD
                GROUP BY 1
            ) as maxft
            ON ft.`id` = maxft.`id`
        );
        """
        self.conn.execute(sql)

        # Create table that combines the two
        sql = """
        CREATE TEMPORARY TABLE tmp_max_filers_with_party (
            INDEX(`filer_id`),
            INDEX(`max_id`),
            INDEX(`party`)
        ) AS (
            SELECT
                max.`filer_id` as `filer_id`,
                max.`max_id` as `max_id`,
                party.party as `party`
            FROM tmp_max_filers as max
            INNER JOIN tmp_max_filer_party as party
            ON max.`filer_id` = party.`filer_id`
        );
        """
        self.conn.execute(sql)

    def drop_temp_tables(self):
        """
        Drop the temporary tables we created as part of this loader.
        """
        self.log(" Dropping temporary tables")
        table_list = [
            "tmp_max_filers",
            "tmp_max_filer_party",
            "tmp_max_filers_with_party",
            "tmp_cand2cmte",
            "tmp_other_filers",
            "tmp_max_other_filers",
        ]
        sql = """DROP TABLE IF EXISTS %s;"""
        for t in table_list:
            self.conn.execute(sql % t)

    def load_candidate_filers(self):
        """
        Load all of the distinct candidate filers into the Filer model.
        """
        self.log(" Loading candidate filers")

        sql = """
        INSERT INTO %s (
            filer_id_raw,
            status,
            effective_date,
            xref_filer_id,
            filer_type,
            name,
            party
        )
        SELECT
            fn.`FILER_ID` as filer_id,
            fn.`STATUS` as status,
            fn.`EFFECT_DT` as effective_date,
            fn.`XREF_FILER_ID` as xref_filer_id,
            'cand' as filer_type,
            REPLACE(
                TRIM(
                    CONCAT(`NAMT`, " ", `NAMF`, " ", `NAML`, " ", `NAMS`)
                ),
                '  ',
                ' '
            ) as name,
            `max`.`party`
        FROM FILERNAME_CD as fn
        INNER JOIN tmp_max_filers_with_party as max
        ON fn.`id` = max.`max_id`
        WHERE fn.`FILER_TYPE` = 'CANDIDATE/OFFICEHOLDER'
        """ % (models.Filer._meta.db_table,)

        self.conn.execute(sql)

    def create_temp_candidate_committee_tables(self):
        self.log(" Creating more temporary tables")
        # Join together via a UNION to return the committee filer ids linked
        # to candidate filer records from either direction (i.e. A or B)
        sql = """
            CREATE TEMPORARY TABLE tmp_cand2cmte (
                INDEX(`candidate_filer_pk`),
                INDEX(`candidate_filer_id`),
                INDEX(`committee_filer_id`)
            )
            SELECT
                f.`id` as candidate_filer_pk,
                f.`filer_id_raw` as candidate_filer_id,
                committee_filer_id_a.`FILER_ID_A` as committee_filer_id
            FROM %(filer_model)s f
            INNER JOIN (
                SELECT DISTINCT `FILER_ID_A`, `FILER_ID_B`
                FROM FILER_LINKS_CD
                WHERE LINK_TYPE = '12011'
                AND `FILER_ID_A` IS NOT NULL
            ) as committee_filer_id_a
            ON f.`filer_id_raw` = committee_filer_id_a.`FILER_ID_B`
            AND f.`filer_id_raw` <> committee_filer_id_a.`FILER_ID_A`

            UNION

            SELECT
                f.`id` as candidate_filer_pk,
                f.`filer_id_raw` as candidate_filer_id,
                committee_filer_id_a.`FILER_ID_B` as committee_filer_id
            FROM %(filer_model)s f
            INNER JOIN (
                SELECT DISTINCT `FILER_ID_A`, `FILER_ID_B`
                FROM FILER_LINKS_CD
                WHERE LINK_TYPE = '12011'
                AND `FILER_ID_B` IS NOT NULL
            ) as committee_filer_id_a
            ON f.`filer_id_raw` = committee_filer_id_a.`FILER_ID_A`
            AND f.`filer_id_raw` <> committee_filer_id_a.`FILER_ID_B`
        """ % dict(filer_model=models.Filer._meta.db_table,)

        self.conn.execute(sql)

    def load_candidate_committees(self):
        """
        Loads the committees associated with candidates into the Committee
        model.
        """
        self.log(" Loading candidate committees")

        sql = """
        INSERT INTO %s (
            filer_id,
            filer_id_raw,
            xref_filer_id,
            name,
            committee_type
        )
        SELECT
            tmp_cand2cmte.`candidate_filer_pk` as filer_id,
            distinct_filers.`filer_id` as filer_id_raw,
            distinct_filers.`xref_filer_id` as xref_filer_id,
            distinct_filers.`name` as name,
            'cand' as committee_type
        FROM tmp_cand2cmte
        INNER JOIN (
            SELECT
                FILERNAME_CD.`FILER_ID` as filer_id,
                FILERNAME_CD.`XREF_FILER_ID` as xref_filer_id,
                REPLACE(
                    TRIM(
                        CONCAT(`NAMT`, " ", `NAMF`, " ", `NAML`, " ", `NAMS`)
                    ),
                    '  ',
                    ' '
                ) as name
            FROM FILERNAME_CD
            INNER JOIN tmp_max_filers
            ON FILERNAME_CD.`id` = tmp_max_filers.`max_id`
        ) as distinct_filers
        ON tmp_cand2cmte.`committee_filer_id` = distinct_filers.`filer_id`;
        """ % (models.Committee._meta.db_table,)

        self.conn.execute(sql)

    def create_temp_pac_tables(self):
        """
        Another set of temporary tables that can't be created until the
        candidates are loaded into our clean models.
        """
        self.log(" Creating yet more temporary tables")

        # Create a table of all committee filer ids that are not
        # linked to candidates.
        #
        # That means committees that:
        #
        #   A) Aren't already in our committee table
        #      as a candidate committee
        #
        #   B) Filed form F460 or F450
        #
        sql = """
            CREATE TEMPORARY TABLE tmp_other_filers (
                index(`filer_id`)
            ) AS (
                SELECT
                    DISTINCT f.`FILER_ID`
                FROM FILER_FILINGS_CD as f
                LEFT OUTER JOIN %(committee_model)s as c
                ON f.`FILER_ID` = c.`filer_id_raw`
                WHERE `FORM_ID` IN ('F460', 'F450')
                AND c.id IS NULL
            );
        """ % dict(committee_model=models.Committee._meta.db_table,)
        self.conn.execute(sql)

        # Now connect those with the FILERNAME_CD table and get
        # the maximum PK there to kill the duplicates
        sql = """
        CREATE TEMPORARY TABLE tmp_max_other_filers (
            index(`filer_id`),
            index(`max_id`)
        ) AS (
            SELECT
                f.`FILER_ID`,
                MAX(`id`) as `max_id`
            FROM FILERNAME_CD as f
            INNER JOIN tmp_other_filers as t
            ON f.`FILER_ID` = t.`filer_id`
            WHERE f.`FILER_TYPE` = 'RECIPIENT COMMITTEE'
            GROUP BY 1
        );
        """
        self.conn.execute(sql)

    def load_pac_filers(self):
        self.log(" Loading PAC filers")
        sql = """
        INSERT INTO %s (
            filer_id_raw,
            status,
            effective_date,
            xref_filer_id,
            filer_type,
            name,
            party
        )
        SELECT
            fn.`FILER_ID` as filer_id,
            fn.`STATUS` as status,
            fn.`EFFECT_DT` as effective_date,
            fn.`XREF_FILER_ID` as xref_filer_id,
            'pac' as filer_type,
            REPLACE(
                TRIM(
                    CONCAT(`NAMT`, " ", `NAMF`, " ", `NAML`, " ", `NAMS`)
                ),
                '  ',
                ' '
            ) as name,
            tmp_max_filer_party.`party`
        FROM FILERNAME_CD as fn
        INNER JOIN tmp_max_other_filers as max
        ON fn.`id` = max.`max_id`
        LEFT OUTER JOIN tmp_max_filer_party
        ON fn.`FILER_ID` = tmp_max_filer_party.`filer_id`
        WHERE fn.`FILER_TYPE` = 'RECIPIENT COMMITTEE';
        """ % (models.Filer._meta.db_table,)

        self.conn.execute(sql)

    def load_pac_committees(self):
        """
        Load PAC filers into the Committee model.
        """
        self.log(" Loading PAC committees")

        sql = """
            INSERT INTO %(committee_model)s (
                filer_id,
                filer_id_raw,
                xref_filer_id,
                name,
                committee_type
            )
            SELECT
                id,
                filer_id_raw,
                xref_filer_id,
                `name`,
                filer_type
            FROM %(filer_model)s
            WHERE filer_type = 'pac'
        """ % dict(
            committee_model=models.Committee._meta.db_table,
            filer_model=models.Filer._meta.db_table,
        )

        self.conn.execute(sql)
