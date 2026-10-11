-- 启用PostGIS扩展
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- 钻孔数据表
CREATE TABLE drillhole (
    id SERIAL PRIMARY KEY,
    hole_id VARCHAR(50) NOT NULL,
    project_name VARCHAR(100),
    location geography(POINT, 4326),
    elevation NUMERIC(8,2),
    depth NUMERIC(8,2),
    azimuth NUMERIC(6,2),
    dip NUMERIC(6,2),
    start_date DATE,
    lithology TEXT,
    ore_grade_li NUMERIC(6,4),
    ore_grade_ta NUMERIC(6,4),
    ore_grade_nb NUMERIC(6,4),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 物探数据表
CREATE TABLE geophysics (
    id SERIAL PRIMARY KEY,
    survey_line VARCHAR(50),
    point_id VARCHAR(50),
    location geography(POINT, 4326),
    resistivity NUMERIC(10,2),
    magnetic NUMERIC(10,2),
    gravity NUMERIC(10,2),
    survey_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 化探数据表
CREATE TABLE geochemistry (
    id SERIAL PRIMARY KEY,
    sample_id VARCHAR(50) NOT NULL,
    location geography(POINT, 4326),
    au_ppb NUMERIC(8,2),
    ag_ppm NUMERIC(8,2),
    cu_ppm NUMERIC(8,2),
    li_ppm NUMERIC(8,2),
    w_ppm NUMERIC(8,2),
    sample_type VARCHAR(30),
    survey_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 矿区边界表
CREATE TABLE mining_area (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    boundary geography(POLYGON, 4326),
    area_km2 NUMERIC(10,2),
    mine_type VARCHAR(50),
    status VARCHAR(30),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 地质图件元数据表
CREATE TABLE geo_document (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    doc_type VARCHAR(50),
    mine_area VARCHAR(100),
    content TEXT,
    publish_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 插入宜春地区示例数据
INSERT INTO mining_area (name, boundary, area_km2, mine_type, status) VALUES
('宜春钽铌矿', ST_GeomFromText('POLYGON((114.3 27.8, 114.5 27.8, 114.5 28.0, 114.3 28.0, 114.3 27.8))', 4326), 12.5, '钽铌锂', '生产中'),
('花桥锂矿', ST_GeomFromText('POLYGON((114.6 27.9, 114.8 27.9, 114.8 28.1, 114.6 28.1, 114.6 27.9))', 4326), 8.3, '锂云母', '生产中'),
('九岭锂矿', ST_GeomFromText('POLYGON((114.9 27.7, 115.1 27.7, 115.1 27.9, 114.9 27.9, 114.9 27.7))', 4326), 15.2, '锂云母', '扩建中');

INSERT INTO drillhole (hole_id, project_name, location, elevation, depth, azimuth, dip, start_date, lithology, ore_grade_li, ore_grade_ta, ore_grade_nb) VALUES
('ZK001', '宜春钽铌矿勘探', ST_GeomFromText('POINT(114.38 27.88)', 4326), 185.5, 320.0, 45.0, 75.0, '2024-03-15', '花岗伟晶岩,钠长石化蚀变明显', 0.32, 0.018, 0.022),
('ZK002', '宜春钽铌矿勘探', ST_GeomFromText('POINT(114.40 27.90)', 4326), 192.3, 280.0, 90.0, 80.0, '2024-04-20', '云英岩化花岗岩,锂云母富集', 0.45, 0.015, 0.019),
('ZK003', '宜春钽铌矿勘探', ST_GeomFromText('POINT(114.42 27.86)', 4326), 178.9, 350.0, 135.0, 70.0, '2024-05-10', '伟晶岩脉,锂辉石可见', 0.28, 0.021, 0.025),
('ZK004', '花桥锂矿详查', ST_GeomFromText('POINT(114.68 27.95)', 4326), 210.5, 260.0, 0.0, 85.0, '2024-06-01', '含锂瓷土矿,品位均匀', 0.38, 0.012, 0.016),
('ZK005', '花桥锂矿详查', ST_GeomFromText('POINT(114.72 28.02)', 4326), 225.0, 300.0, 180.0, 78.0, '2024-07-15', '花岗岩风化壳,锂云母含量高', 0.42, 0.010, 0.014),
('ZK006', '九岭锂矿勘探', ST_GeomFromText('POINT(114.95 27.78)', 4326), 165.8, 400.0, 270.0, 82.0, '2024-08-20', '伟晶岩脉群,锂辉石+锂云母', 0.55, 0.008, 0.011),
('ZK007', '九岭锂矿勘探', ST_GeomFromText('POINT(115.02 27.82)', 4326), 172.3, 380.0, 315.0, 76.0, '2024-09-05', '钠长石花岗岩,强蚀变带', 0.35, 0.013, 0.017);

INSERT INTO geochemistry (sample_id, location, au_ppb, ag_ppm, cu_ppm, li_ppm, w_ppm, sample_type, survey_date) VALUES
('GH001', ST_GeomFromText('POINT(114.39 27.89)', 4326), 2.5, 0.8, 35.0, 2800.0, 12.0, '土壤', '2024-04-01'),
('GH002', ST_GeomFromText('POINT(114.41 27.91)', 4326), 1.8, 1.2, 28.0, 3500.0, 8.0, '土壤', '2024-04-01'),
('GH003', ST_GeomFromText('POINT(114.70 27.98)', 4326), 3.2, 0.5, 42.0, 4200.0, 15.0, '岩石', '2024-05-15'),
('GH004', ST_GeomFromText('POINT(114.98 27.80)', 4326), 4.1, 2.1, 55.0, 5100.0, 22.0, '岩石', '2024-06-20'),
('GH005', ST_GeomFromText('POINT(115.00 27.84)', 4326), 2.8, 1.5, 38.0, 3800.0, 18.0, '土壤', '2024-06-20');

INSERT INTO geo_document (title, doc_type, mine_area, content, publish_date) VALUES
('宜春钽铌矿地质勘查报告', '勘查报告', '宜春钽铌矿', '宜春钽铌矿位于江西省宜春市，是一个大型的钽铌锂多金属矿床。矿床类型为花岗伟晶岩型，主要含矿岩石为钠长石化锂云母花岗岩。矿区出露地层主要为震旦系和寒武系浅变质岩，岩浆岩为燕山期花岗岩。成矿作用与花岗岩的结晶分异和晚期交代作用密切相关。钠长石化和云英岩化是主要的蚀变类型，锂云母、锂辉石是主要含锂矿物。', '2024-01-15'),
('花桥锂矿资源储量核实报告', '储量报告', '花桥锂矿', '花桥锂矿矿床赋存于燕山期花岗岩风化壳中，含矿层主要由含锂瓷土矿组成。矿体呈层状、似层状产出，产状与地形基本一致。矿石自然类型为花岗岩风化壳型含锂瓷土矿，工业类型为锂云母型锂矿。Li2O平均品位0.35%-0.45%，属于低品位大型矿床。', '2024-03-20'),
('九岭锂矿勘探地质报告', '勘探报告', '九岭锂矿', '九岭锂矿位于宜春市奉新县，矿区面积约15平方公里。已发现多条伟晶岩脉，走向北东，倾向南东，倾角60-80度。主要矿物为锂辉石、锂云母、铌钽铁矿等。Li2O品位0.3%-0.6%，局部富集可达0.8%以上。矿床规模达大型，是宜春地区重要的锂资源基地。', '2024-06-10');

CREATE INDEX idx_drillhole_location ON drillhole USING GIST(location);
CREATE INDEX idx_geophysics_location ON geophysics USING GIST(location);
CREATE INDEX idx_geochemistry_location ON geochemistry USING GIST(location);
CREATE INDEX idx_mining_area_boundary ON mining_area USING GIST(boundary);
