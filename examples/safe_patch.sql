-- Release 2.4.1 - corrected version of risky_patch.sql
ALTER TABLE land_parcel ALTER COLUMN area TYPE numeric(16,5);
ALTER TABLE land_parcel ALTER COLUMN area_surveyed TYPE numeric(16,5);
ALTER TABLE land_parcel ALTER COLUMN area_approved TYPE numeric(16,5);

-- text to integer conversion that legitimately uses its own column
ALTER TABLE application ALTER COLUMN lot_no TYPE integer USING trim(lot_no)::integer;

ALTER TABLE application ADD COLUMN district_code varchar(10) DEFAULT 'UNK' NOT NULL;
DELETE FROM ref_status_code WHERE is_active = 'N';

-- sequence resync, Oracle style: literal gap, bump, reset
ALTER SEQUENCE seq_application INCREMENT BY 343;
SELECT seq_application.NEXTVAL FROM dual;
ALTER SEQUENCE seq_application INCREMENT BY 1;
