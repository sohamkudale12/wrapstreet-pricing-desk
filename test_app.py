from streamlit.testing.v1 import AppTest
for page in ["Price desk", "Chain view", "How it works"]:
    for sid in ["S01", "S06", "S08", "S03"]:
        at = AppTest.from_file("app.py", default_timeout=120)
        at.session_state["store"] = sid
        at.session_state["product"] = "P02"
        at.run()
        at.radio(key="page").set_value(page).run()
        assert not at.exception, (page, sid, at.exception)
        if page != "Price desk": break
    print(page, "ok")
# every store x product on price desk
at = AppTest.from_file("app.py", default_timeout=120); at.run()
for sid in ["S01","S02","S03","S04","S05","S06","S07","S08"]:
    for pid in ["P01","P02","P03","P04","P05","P06"]:
        at.selectbox(key="store").set_value(sid); at.selectbox(key="product").set_value(pid); at.run()
        assert not at.exception, (sid, pid, at.exception)
print("all 48 ok")
# shortcut button + slider changes
at.button[1].click().run(); assert at.session_state["store"] == "S06" and not at.exception
at.slider[0].set_value(5).run(); assert not at.exception
print(at.title[0].value)
