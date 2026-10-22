#!/usr/bin/env python3
"""生成 china_address_dict 全量数据（全国区县级）。

数据源：阿里 DataV 行政区划边界数据（geo.datav.aliyun.com/areas_v3），
含每个区县的 adcode 与中心点坐标。闲鱼 divisionId 即 adcode；
gps 取区县中心点，poi_name 统一取「{区县}人民政府」（各级政府驻地是
最稳定的行政区划 POI 名称），poi_id 与 division_id 一致
（2026-10-22 实测：该组合可被闲鱼发布接口 mtop.idle.pc.idleitem.publish 接受）。

用法：python3 build_address_dict.py [输出SQL路径]
产物：address_dict.sql（INSERT ... ON DUPLICATE KEY UPDATE，可重复执行）。
"""
import json
import subprocess
import sys
import os

BASE = "https://geo.datav.aliyun.com/areas_v3/bound"
RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
CURL = "/usr/bin/curl" if os.path.exists("/usr/bin/curl") else "curl"

PROVINCES = {
    110000: "北京市", 120000: "天津市", 130000: "河北省", 140000: "山西省",
    150000: "内蒙古自治区", 210000: "辽宁省", 220000: "吉林省",
    230000: "黑龙江省", 310000: "上海市", 320000: "江苏省", 330000: "浙江省",
    340000: "安徽省", 350000: "福建省", 360000: "江西省", 370000: "山东省",
    410000: "河南省", 420000: "湖北省", 430000: "湖南省", 440000: "广东省",
    450000: "广西壮族自治区", 460000: "海南省", 500000: "重庆市",
    510000: "四川省", 520000: "贵州省", 530000: "云南省", 540000: "西藏自治区",
    610000: "陕西省", 620000: "甘肃省", 630000: "青海省", 640000: "宁夏回族自治区",
    650000: "新疆维吾尔自治区", 710000: "台湾省", 810000: "香港特别行政区",
    820000: "澳门特别行政区",
}
MUNICIPALITIES = {110000, 120000, 310000, 500000}


def fetch(adcode: int) -> dict:
    """下载并解析某区划的 _full 数据；DataV 不提供该文件时（如济源等
    省直辖县级单位没有下级区县文件）返回空 FeatureCollection，
    由上层以其自身作为一条区县记录兜底。"""
    path = os.path.join(RAW_DIR, f"{adcode}_full.json")
    if not os.path.exists(path):
        url = f"{BASE}/{adcode}_full.json"
        subprocess.run([CURL, "-sL", "-o", path, url], check=True)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict) or "features" not in doc:
            raise ValueError("unexpected payload")
        return doc
    except (ValueError, json.JSONDecodeError):
        empty = {"type": "FeatureCollection", "features": []}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(empty, fh)
        return empty


def features_by_level(doc: dict, level: str) -> list:
    return [f["properties"] for f in doc.get("features", [])
            if f.get("properties", {}).get("level") == level]


def gps_of(props: dict) -> str:
    center = props.get("center") or props.get("centroid")
    if not center or len(center) != 2:
        return ""
    return f"{center[0]},{center[1]}"


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


def main() -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    rows = {}  # adcode -> tuple

    for prov_code, prov_name in PROVINCES.items():
        prov_doc = fetch(prov_code)
        cities = features_by_level(prov_doc, "city")
        # 个别省级文件直接挂区县（如港澳），一并收集
        direct_districts = features_by_level(prov_doc, "district")
        for d in direct_districts:
            cities.append({"adcode": prov_code, "name": prov_name,
                           "center": d.get("center"), "_self_district": d})

        for city in cities:
            city_code = int(city["adcode"])
            city_name = city["name"]
            if city.get("_self_district") is not None:
                districts = [city["_self_district"]]
            else:
                city_doc = fetch(city_code)
                districts = features_by_level(city_doc, "district")
            if not districts:
                # 省直辖县级单位等无下级区县者：以自身作为一条区县记录
                districts = [city]

            if prov_code in MUNICIPALITIES:
                display_city = prov_name
            elif str(city_code)[2:4] == "90":
                display_city = "省直辖县级行政区划"
            else:
                display_city = city_name

            for d in districts:
                adcode = str(d["adcode"])
                area = d["name"]
                gps = gps_of(d) or gps_of(city)
                if not gps:
                    continue
                full_name = prov_name + display_city + area \
                    if display_city != area else prov_name + area
                if display_city == prov_name:
                    full_name = prov_name + area
                rows[adcode] = (
                    adcode, prov_name, display_city, area, full_name,
                    adcode, gps, gps, adcode, f"{area}人民政府", full_name,
                )

    out_path = sys.argv[1] if len(sys.argv) > 1 else "address_dict.sql"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("-- china_address_dict 全量初始化（全国区县，数据源 DataV 行政区划）\n")
        fh.write("-- 可重复执行：按 adcode 唯一键 upsert\n")
        batch = []
        for r in rows.values():
            batch.append(
                "('%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','success')"
                % tuple(esc(str(x)) for x in r)
            )
        for i in range(0, len(batch), 200):
            chunk = ",\n".join(batch[i:i + 200])
            fh.write(
                "INSERT INTO china_address_dict "
                "(adcode, prov, city, area, full_name, division_id, gps, gps_center, "
                "poi_id, poi_name, detail, sync_status) VALUES\n"
                + chunk
                + "\nON DUPLICATE KEY UPDATE prov=VALUES(prov), city=VALUES(city), "
                  "area=VALUES(area), full_name=VALUES(full_name), "
                  "division_id=VALUES(division_id), gps=VALUES(gps), "
                  "gps_center=VALUES(gps_center), poi_id=VALUES(poi_id), "
                  "poi_name=VALUES(poi_name), detail=VALUES(detail), "
                  "sync_status='success';\n"
            )
    print(f"rows={len(rows)} -> {out_path}")


if __name__ == "__main__":
    main()
