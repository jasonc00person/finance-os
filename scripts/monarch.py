#!/usr/bin/env python
"""Monarch Money CLI (unofficial API via monarchmoneycommunity).

Run with .venv/bin/python. Session lives in .mm/mm_session.pickle.

  auth                          one-time interactive login (the owner runs this; prompts
                                for email/password/MFA, saves session for reuse)
  accounts                      all accounts: name, institution, type, balance, id
  transactions [args]           JSON dump. --start/--end YYYY-MM-DD, --limit N
                                (default 1000), --account <id>, --needs-review
  categories                    category id, name, group
  tags                          tag id, name
  update <tx_id> [args]         --category <id>, --notes <text>, --reviewed,
                                --hide (hide from reports)
  refresh                       ask Monarch to re-sync all connected institutions
  raw <method> [json-kwargs]    call any library method, e.g.
                                raw get_cashflow_summary '{"start_date":"2026-01-01"}'

If any command dies with 401/session errors, rerun `auth`.
"""

import asyncio
import json
import sys

from monarchmoney import MonarchMoney


def out(data):
    print(json.dumps(data, indent=2, default=str))


async def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]

    mm = MonarchMoney()

    if cmd == "auth":
        await mm.interactive_login()
        who = await mm.get_subscription_details()
        print("Login OK, session saved to .mm/mm_session.pickle")
        out(who)
        return

    try:
        mm.load_session()
    except FileNotFoundError:
        sys.exit("No session found. Run `.venv/bin/python monarch.py auth` first (interactive login).")

    if cmd == "accounts":
        data = await mm.get_accounts()
        rows = [
            {
                "id": a["id"],
                "name": a["displayName"],
                "institution": (a.get("institution") or {}).get("name"),
                "type": (a.get("type") or {}).get("display"),
                "balance": a.get("displayBalance"),
                "lastUpdate": a.get("updatedAt"),
            }
            for a in data["accounts"]
        ]
        out(rows)

    elif cmd == "transactions":
        kw = {"limit": 1000}
        it = iter(rest)
        for a in it:
            if a == "--start":
                kw["start_date"] = next(it)
            elif a == "--end":
                kw["end_date"] = next(it)
            elif a == "--limit":
                kw["limit"] = int(next(it))
            elif a == "--account":
                kw["account_ids"] = [next(it)]
            elif a == "--needs-review":
                kw["needs_review"] = True
        out(await mm.get_transactions(**kw))

    elif cmd == "categories":
        data = await mm.get_transaction_categories()
        rows = [
            {"id": c["id"], "name": c["name"], "group": (c.get("group") or {}).get("name")}
            for c in data["categories"]
        ]
        out(rows)

    elif cmd == "tags":
        out(await mm.get_transaction_tags())

    elif cmd == "update":
        tx_id, kw = rest[0], {}
        it = iter(rest[1:])
        for a in it:
            if a == "--category":
                kw["category_id"] = next(it)
            elif a == "--notes":
                kw["notes"] = next(it)
            elif a == "--reviewed":
                kw["reviewed"] = True
            elif a == "--hide":
                kw["hide_from_reports"] = True
        out(await mm.update_transaction(tx_id, **kw))

    elif cmd == "refresh":
        accounts = await mm.get_accounts()
        ids = [a["id"] for a in accounts["accounts"]]
        ok = await mm.request_accounts_refresh(ids)
        print(f"refresh requested for {len(ids)} accounts: {ok}")

    elif cmd == "raw":
        method = getattr(mm, rest[0])
        kw = json.loads(rest[1]) if len(rest) > 1 else {}
        out(await method(**kw))

    else:
        print(f"unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
