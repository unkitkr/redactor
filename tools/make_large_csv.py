#!/usr/bin/env python3
"""Generate a large synthetic CSV in the same family as input/encounters.csv.

    python tools/make_large_csv.py --size-gb 2 --out big_encounters.csv [--seed 1]

Streams to disk (constant memory). Same columns, encoding (UTF-8 with BOM), CRLF line
endings and quoting rules as encounters.csv, including multiline quoted comments.
All data is synthetic. Your pipeline must process the whole file within the A7 limits.
"""
import argparse, csv, datetime as dt, os, random, sys

FIRST = ["Daniel", "Priya", "Marcus", "Elena", "Tobias", "Nadia", "Arjun", "Lucia", "Gregory", "Meera", "Oliver",
         "Hannah", "Samuel", "Ayesha", "Victor", "Ingrid", "Rahul", "Clara", "Desmond", "Farah", "Renée", "Zoë"]
LAST = ["Okafor", "Lindqvist", "Brennan", "Kapoor", "Halvorsen", "Delacroix", "Whitfield", "Nakamura", "Castellano",
        "Pritchard", "Ashworth", "Venkataraman", "Moreau", "Gallagher", "Szabo", "Iyer", "Fairbanks", "Quintero"]
DX = [("E11.9", "metformin 500 mg BID"), ("I10", "lisinopril 10 mg daily"), ("J45.909", "albuterol 90 mcg PRN"),
      ("G20", "carbidopa-levodopa 25/100 TID"), ("N18.3", "renal diet"), ("J18.9", "amoxicillin 875 mg BID")]
CPT = ["99213", "99214", "99223", "71046", "80053"]
COLS = ["encounter_id", "mrn", "patient", "birth_date", "sex", "admit_ts", "discharge_ts", "attending",
        "attending_npi", "dx_codes", "cpt_codes", "lot_no", "contact", "comments"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size-gb", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    r = random.Random(a.seed)
    target = int(a.size_gb * 1024 ** 3)
    docs = [(f"{r.choice(FIRST)} {r.choice(LAST)}", "%d" % r.randint(10 ** 9, 2 * 10 ** 9 - 1)) for _ in range(400)]
    base = dt.datetime(2026, 1, 1)
    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(COLS)
        i = 0
        while True:
            if i % 5000 == 0:
                f.flush()
                if f.tell() >= target:
                    break
            fn, ln = r.choice(FIRST), r.choice(LAST)
            dob = dt.date(1930, 1, 1) + dt.timedelta(days=r.randint(0, 33000))
            adm = base + dt.timedelta(minutes=r.randint(0, 525600))
            dis = adm + dt.timedelta(hours=r.randint(2, 200))
            dx, med = r.choice(DX)
            doc = r.choice(docs)
            phone = "%03d-555-%04d" % (r.choice([206, 312, 415, 512, 617, 802]), r.randint(100, 199))
            name = f"{fn} {ln}" if r.random() < 0.8 else f"{ln}, {fn}"
            comment = r.choice([
                f'Pt states "ok".\nCall {phone} before {dis:%m/%d/%Y}.',
                f"{med}, f/u in 2 weeks.",
                f"Lives at {r.randint(10, 9999)} Orchard Street; spouse {r.choice(FIRST)} assists.",
                f"Age {(adm.date() - dob).days // 365}. No acute distress.",
            ])
            w.writerow(["ENC%09d" % i, "00%05d" % r.randint(10000, 99999), name, dob.strftime("%m/%d/%Y"),
                        r.choice("MF"), adm.strftime("%Y-%m-%d %H:%M"), dis.strftime("%Y-%m-%d %H:%M"),
                        f"Dr. {doc[0]}", doc[1], dx, r.choice(CPT), "%07d" % r.randint(10 ** 6, 10 ** 7 - 1),
                        phone.replace("-", "") if r.random() < 0.3 else phone, comment])
            i += 1
    print(f"wrote {i:,} rows, {os.path.getsize(a.out) / 1024 ** 3:.2f} GB -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
