CREDENTIALS = []


email = "test-{}@testing.bitahoy.com"
password = "Bitahoy_testpassword_{}"
wdcode = "10000000000000{}"
for i in range(0, 20):
    user_email = email.format(i)
    user_password = password.format(i)
    i_doubledigit = "{0:0=2d}".format(i)
    user_wdcode = wdcode.format(i_doubledigit)
    CREDENTIALS.append({"WDCODE": user_wdcode, "SECRET": "[redacted-7]", "EMAIL": user_email,
                        "PASSWORD": user_password})
