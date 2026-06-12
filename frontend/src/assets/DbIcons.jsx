/* Database type brand icons — SVGs from simpleicons.org (CC0) */

function SvgIcon({ src, size }) {
  return (
    <span
      className="inst-type-icon"
      style={{
        display: "inline-flex",
        width: size,
        height: size,
        background: `url(${src}) center/contain no-repeat`,
        flexShrink: 0,
      }}
    />
  );
}

import mysqlSvg from "./icon-mysql.svg";
import mariadbSvg from "./icon-mariadb.svg";
import postgresqlSvg from "./icon-postgresql.svg";
import mongodbSvg from "./icon-mongodb.svg";

export function IconMySQL({ size = 18 })       { return <SvgIcon src={mysqlSvg} size={size} />; }
export function IconMariaDB({ size = 18 })     { return <SvgIcon src={mariadbSvg} size={size} />; }
export function IconPostgreSQL({ size = 18 })  { return <SvgIcon src={postgresqlSvg} size={size} />; }
export function IconMongoDB({ size = 18 })     { return <SvgIcon src={mongodbSvg} size={size} />; }

export function resolveDbIcon(dbType, dbVersion) {
  if (dbType === "postgresql") return IconPostgreSQL;
  if (dbType === "mongodb") return IconMongoDB;
  if (dbVersion && /MariaDB/i.test(dbVersion)) return IconMariaDB;
  return IconMySQL;
}

export function resolveDbLabel(dbType, dbVersion) {
  if (dbType === "postgresql") return "PostgreSQL";
  if (dbType === "mongodb") return "MongoDB";
  if (dbVersion && /MariaDB/i.test(dbVersion)) return "MariaDB";
  return "MySQL";
}
