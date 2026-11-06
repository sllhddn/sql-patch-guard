-- Release 2.4.0 - land parcel area precision change (fictional example)
-- Widen area columns from numeric(16,4) to numeric(16,5)

ALTER TABLE land_parcel ALTER COLUMN area TYPE numeric(16,5);

-- copy-pasted lines: USING still points at "area" -> every row gets area's value
ALTER TABLE land_parcel ALTER COLUMN area_surveyed TYPE numeric(16,5) USING area::numeric(16,5);
ALTER TABLE land_parcel ALTER COLUMN area_approved TYPE numeric(16,5) USING area::numeric(16,5);

-- narrowing a column that already holds long remarks
ALTER TABLE application ALTER COLUMN remarks TYPE varchar(100);

-- new mandatory column on a table that already has data
ALTER TABLE application ADD COLUMN district_code varchar(10) NOT NULL;

-- clean up a lookup table... without a WHERE clause
DELETE FROM ref_status_code;

-- resync the sequence (Oracle does not evaluate this expression)
ALTER SEQUENCE seq_application INCREMENT BY 50213 - 49870;

ALTER TABLE land_parcel ALTER COLUMN area TYPE numeric(16,5);
