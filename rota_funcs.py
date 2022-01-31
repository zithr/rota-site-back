from dataclasses import dataclass
from typing import List, Tuple, Union
import math
import re
import requests
import pendulum
import asyncio
import aiohttp
import time, json
from loguru import logger
from env.secret import login_info
from bs4 import BeautifulSoup


@dataclass()
class RotaBro:
    shift_id: str
    date: str
    time: str
    type: str
    vols: List[str]
    vol_shift_id: List[str]
    dt_obj: pendulum.DateTime
    
    def toJSON(self):
        return json.dumps(self, default=lambda i: i.__dict__, sort_keys=True, indent=4)

@dataclass()
class VolBro:
    id: str
    name: str
    rota: List[str]


# Main sign up function
# Make edits to rota and vol name here
async def make_sign_ups(
    session, name: str, pattern, start_date: pendulum.DateTime, rota_length=6
):
    vol = get_vol_by_name(session, name)
    assert vol
    # pattern = [
    #     ["Monday 19:00-22:00", "Tuesday 19:00-22:00"],
    #     ["OFF"],
    #     ["OFF"],
    #     ["OFF"],
    #     ["Thursday 22:30-01:00"],
    #     ["Thursday 19:00-22:00"],
    #     ["Wednesday 19:00-22:00"],
    #     ["Friday 19:00-22:00"],
    # ]
    # start_date = input("Enter start date (dd.mm.yyyy)\n")
    # start_date = pendulum.from_format(start_date, "DD.MM.YYYY")
    dates = pattern_to_dates(session, pattern, start_date, rota_length)
    rota = await abuild_rota_data(
        session, start_date, start_date.add(months=rota_length)
    )
    exp, skip = dates_to_shift_ids(dates, rota)
    sign, blocked = verify_shify_ready_for_signup(vol, exp)
    print("***********************************")
    if skip:
        for shift in skip:
            print(f"shift not found on rota: {shift.format('DD MMM YY @ HHmm')}")
    if blocked:
        for shift in blocked:
            print(
                f"shift already has 2 vols: {shift.dt_obj.format('DD MMM YY @ HHmm')}"
            )
    for shift in sign:
        print(f"signup for: {shift.dt_obj.format('DD MMM YY @ HHmm')}")
    # if (
    #     sg.PopupOKCancel(
    #         f"Make {len(sign)} sign ups for {vol.name} ({len(skip)} shifts skipped)\nStarting with: {sign[0].dt_obj.format('DD MMM YY @ HHmm')}\nEnding with {sign[-1].dt_obj.format('DD MMM YY @ HHmm')}"
    #     )
    #     != "OK"
    # ):
    #     return
    print("apost_all")
    await apost_all_sign_ups(session, vol, sign)
    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # asyncio.run(apost_all_sign_ups(session, vol, sign))
    return True
    # if (
    #     input(f"Make {len(sign)} sign ups for {vol.name} ({len(skip)} shifts skipped)")
    #     == "y"
    # ):
    #     print("Posting sign ups...")
    #     post_all_sign_ups(session, vol, sign)


# Main remove sign up function, untested
# Make edits to remove sign ups here
def remove_sign_ups(session):
    vol = get_vol_by_name(s, "Natashaj 1928")
    start_date = input("Enter start date (dd.mm.yyyy)\n")
    start_date = pendulum.from_format(start_date, "DD.MM.YYYY")
    end_date = start_date.add(weeks=8)
    # remove_all_sign_ups(session, vol, start_date, end_date)


def get_week_number(session, date: pendulum.DateTime) -> int:
    rota = get_rota(session, date)
    week_num = rota[0].type
    return int(re.search(r"\d+", week_num).group())


def get_week_number_gui(
    session, date: pendulum.DateTime, gui_start=False
) -> Union[int, dict]:
    rota = get_rota(session, date)
    week_num = rota[0].type
    if gui_start:
        vol_shifts = {}
        for shift in rota:
            if shift.dt_obj < pendulum.now() or not shift.vols:
                continue
            for vol in shift.vols:
                if vol == "[sign up]" or "Week" in vol:
                    continue
                if vol in vol_shifts:
                    vol_shifts[vol].append(shift.dt_obj)
                else:
                    vol_shifts[vol] = [shift.dt_obj]
    return int(re.search(r"\d+", week_num).group()), vol_shifts


def rota_pattern_to_dates(
    session, pattern, start_date: pendulum.DateTime, rota_length: int = 6
) -> List[str]:
    if len(pattern) != 8:
        print(f"Pattern is {len(pattern)} instead of 8 weeks long")
    end_date = start_date.add(months=rota_length)
    date = start_date.start_of("week")
    week_num = get_week_number(session, date)  # need to load rota to get week number??
    print(f"Week number of {start_date.format('DD.MM.YY')} is {week_num}")
    shifts = []
    for i in range(rota_length * 4):
        week = ((week_num + i - 1) % 8) + 1
        week = f"Week {week}"
        for day in pattern[week]:
            for shift in pattern[week][day]:
                if date > end_date:
                    return shifts
                shift = shift.replace(" ", "")
                shift_start_time = shift.split("-")[0]
                date = date.at(int(shift_start_time[:2]), int(shift_start_time[2:4]))
                if date >= start_date:
                    shifts.append(date)
            date = date.add(days=1)
    return shifts


def pattern_to_dates(
    session, pattern, start_date: pendulum.DateTime, rota_length: int = 6
) -> List[str]:  # number of months to create shifts for
    if len(pattern) != 8:
        print(f"Pattern is {len(pattern)} instead of 8 weeks long")
    date = start_date.start_of("week")
    print("Rota fetch for week num... ", end="")
    week_num = get_week_number(session, date)  # need to load rota to get week number??
    shifts = []
    for i in range(rota_length * 4):
        week = (week_num + i - 1) % 8
        for shift in pattern[week]:
            if isinstance(shift, int):
                pass
            elif len(shift) < 6:
                pass
            else:
                day_of_week = shift.split(" ")[0]
                weekday = pendulum.from_format(day_of_week, "dddd").day_of_week
                shift_time = shift.split(" ")[1].replace(":", "")

                if weekday == 1:
                    dt = pendulum.from_format(
                        f'{date.day} {date.month} {date.year} {shift_time.split("-")[0]}',
                        "D M YYYY HHmm",
                        # tz="Europe/London",
                    )
                    if dt > start_date:
                        shifts.append(dt)
                else:
                    real_date = date.next(weekday)
                    dt = pendulum.from_format(
                        f'{real_date.day} {real_date.month} {real_date.year} {shift_time.split("-")[0]}',
                        "D M YYYY HHmm",
                        # tz="Europe/London",
                    )
                    if dt > start_date:
                        shifts.append(dt)

        date = date.add(days=7)
    return shifts


def dates_to_shift_ids(
    pattern: List[pendulum.DateTime], rota: List[RotaBro]
) -> Tuple[RotaBro, pendulum.DateTime]:
    expected_shifts = []
    skipped_shifts = []
    for shift in pattern:
        for check_shift in rota:
            if check_shift.dt_obj > shift:
                print(
                    f"{shift.format('DD MMM HHmm')} not found on rota, {check_shift.dt_obj} > {shift}"
                )
                skipped_shifts.append(shift)
                break
            if check_shift.dt_obj == shift and check_shift.type == "(Duty Room)":
                print(
                    f"Matched shift {shift.format('DD MMM HHmm')} shift_id: {check_shift.shift_id}"
                )
                expected_shifts.append(check_shift)
                break
    return expected_shifts, skipped_shifts


def verify_shify_ready_for_signup(
    volunteer: VolBro, expected_shifts: List[RotaBro]
) -> Tuple[RotaBro, RotaBro]:
    ready_to_sign_shifts = []
    blocked_shifts = []
    for shift in expected_shifts:
        if shift.dt_obj < pendulum.today():
            continue
        if volunteer.name in shift.vols:
            print(f"vol already signed up for {shift.date.format('DD MMM HHmm')}")
        elif "[sign up]" not in shift.vols:
            print(
                f"No room for vol in {shift.date.format('DD MMM HHmm')}, already signed: {shift.vols}"
            )
            blocked_shifts.append(shift)
        else:
            ready_to_sign_shifts.append(shift)
    return ready_to_sign_shifts, blocked_shifts


def get_vol_by_name(s, name: str) -> VolBro:
    vols = get_active_volunteers(s)
    for vol in vols:
        if vol.name == name:
            return vol
    return None


def get_vol_by_id(s, id: str) -> VolBro:
    vols = get_active_volunteers(s)
    for vol in vols:
        if vol.id == id:
            return vol


def get_vol_shifts_by_name(
    s, name: str, upcoming_only: bool = False
) -> List[pendulum.DateTime]:
    vol = get_vol_by_name(s, name)
    if not vol:
        print(f"Vol: {name} not found")
        return None
    return get_vol_shifts_by_id(s, vol.id, upcoming_only)


def get_vol_shifts_by_id(
    s, id: str, upcoming_only: bool = False
) -> List[pendulum.DateTime]:
    res = s.get(
        f"https://www.3r.org.uk/directory/{id}",
    )
    soup = BeautifulSoup(res.content, "html.parser")
    results = soup.find(class_="directory_stats_rota")
    shifts = results.find_all(class_="stats_duty_complete")
    shift_titles = []
    for shift in shifts:
        shift_data = shift["title"].split(" to")[0]
        dt_shift_data = pendulum.from_format(
            shift_data, "dddd DD MMMM YYYY [(from] HH:mm"
        )
        if upcoming_only and dt_shift_data < pendulum.today():
            continue
        shift_titles.append(dt_shift_data)

    return shift_titles


def get_active_volunteers(session) -> List[VolBro]:
    res = session.get(
        f"https://www.3r.org.uk/rota/sign_up_bin",
    )
    soup = BeautifulSoup(res.content, "html.parser")
    results = soup.find_all(class_="volunteer_link")
    vols = []
    for vol in results:
        vol_id = vol["href"].split("/")[-1]
        vol_name = vol["title"]
        if vol_name.strip() == "Week Number":
            continue
        vols.append(VolBro(id=vol_id, name=vol_name, rota=[]))

    return vols


def post_all_sign_ups(session, volunteer: VolBro, shifts: List[RotaBro]):
    for shift in shifts:
        form_data = {"vol_id": volunteer.id, "shift_id": shift.shift_id}
        print(f"Signing: {shift.dt_obj.format('DD MMM YY @ HHmm')}")
        post_sign_up(session, form_data)


async def apost_all_sign_ups(
    _session, volunteer: VolBro, shifts: List[RotaBro]
) -> List[str]:
    auth = aiohttp.BasicAuth(
        login=login_info["username"], password=login_info["password"], encoding="utf-8"
    )
    async with aiohttp.ClientSession(
        auth=auth, connector=aiohttp.TCPConnector(limit=5)
    ) as session:
        tasks = []
        res = []
        i = 0
        for shift in shifts:
            form_data = {"vol_id": volunteer.id, "shift_id": shift.shift_id}
            readable_dt = shift.dt_obj.format("DD MMM YY @ HHmm")
            print(f"Signing: {readable_dt}")
            tasks.append(
                asyncio.create_task(apost_sign_up(session, form_data, readable_dt))
            )
        for coro in asyncio.as_completed(tasks):
            res.append(await coro)
            # sg.one_line_progress_meter("Signing Up", i + 1, len(tasks))
            i += 1
        print(f"Pushed {volunteer.name}'s rota to site")
    #     responses = await asyncio.gather(*tasks)
    # print(responses)
    success_signs = [x for x in res if x == 1]
    fail_signs = [", ".join(x) for x in res if x != 1]
    if fail_signs:
        # sg.Popup(
        #     f"{len(success_signs)} sign ups made for {volunteer.name}, {len(shifts)-len(success_signs)} errors:\n {fail_signs}",
        #     keep_on_top=True,
        # )
        return res
    # sg.Popup(
    #     f"{len(success_signs)} sign ups made for {volunteer.name}, {len(shifts)-len(success_signs)} errors:\n",
    #     keep_on_top=True,
    # )
    return res

    # async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=10)) as session:
    #     tasks = []
    #     for i in range(1,9):
    #         tasks.append(asyncio.create_task(apost_sign_up(session, i)))
    #     responses = await asyncio.gather(*tasks)
    # print(responses)

    # for shift in shifts:
    #     form_data = {"vol_id": volunteer.id, "shift_id": shift.shift_id}
    #     print(f"Signing: {shift.dt_obj.format('DD MMM YY @ HHmm')}")
    #     post_sign_up(session, form_data)


def remove_all_sign_ups(
    session,
    volunteer: VolBro,
    date_start: pendulum.DateTime,
    date_end: pendulum.DateTime,
    shift_types: List[str] = None,
) -> int:
    vol_shift_ids_to_remove = []
    rota = build_rota_data(session, date_start, date_end)
    for shift in rota:
        for v, vsid in zip(shift.vols, shift.vol_shift_id):
            if v == volunteer.name:
                if shift_types:
                    if shift.type not in shift_types:
                        continue
                vol_shift_ids_to_remove.append(vsid)
                print(f"Removing from: {shift.date.format('DD MMM YY @ HHmm')}")
    # if (
    #     sg.PopupOK(
    #         f"Remove {volunteer.name} from {len(vol_shift_ids_to_remove)} shifts"
    #     )
    #     != "OK"
    # ):
    #     return
    for i, id in enumerate(vol_shift_ids_to_remove):
        # if not sg.one_line_progress_meter(
        #     "Removing sign up...", i + 1, len(vol_shift_ids_to_remove)
        # ):
        #     break
        post_remove_sign_up(session, id)
    return len(vol_shift_ids_to_remove)


def post_sign_up(session, form_data):  # form_data: vol_id, shift_id
    data = {"volunteer_shift[volunteer_id]": f"{form_data['vol_id']}"}
    r = session.post(f'https://www.3r.org.uk/rota/signup/{form_data["shift_id"]}', data)
    print(f"Sign status: {r.ok}")


async def apost_sign_up(
    session, form_data, readable_dt: str
):  # form_data: vol_id, shift_id
    data = {"volunteer_shift[volunteer_id]": f"{form_data['vol_id']}"}
    async with session.post(
        f"https://www.3r.org.uk/rota/signup/{form_data['shift_id']}", data=data
    ) as response:
        if response.status != 200:
            return f"{readable_dt} Status: {response.status}"
        await response.read()
    return 1
    # logger.info(f"in get {form_data}")
    # async with session.get(
    #     f"https://reqres.in/api/products/{form_data}"
    # ) as response:
    #     await asyncio.sleep(1)
    #     assert response.status == 200
    #     r = await response.read()
    #     logger.info(f"received {form_data} res")
    #     return r


def post_remove_sign_up(session, vol_shift_id):  # needs vol-shift-id
    r = session.post(f"https://www.3r.org.uk/rota/pull_out/{vol_shift_id}")


def make_dt_obj(
    date: pendulum.Date, time: str
) -> str:  # 22:00 - 01:00
    hour, minute = time.split(" -")[0].split(":")
    return pendulum.datetime(date.year, date.month, date.day, int(hour), int(minute)).__str__()



async def abuild_rota_data(
    cookies = None, start_date: pendulum.DateTime = None, end_date: pendulum.DateTime = None, queue = None
):
    if not start_date and not end_date:
        start_date = pendulum.today()
        end_date = start_date.add(weeks=4)
    if not end_date:
        end_date = start_date.add(weeks=4)
    if not cookies:
        logger.info("No Cookie login")
        auth = aiohttp.BasicAuth(
            login=login_info["username"], password=login_info["password"], encoding="utf-8"
        )
    else:
        auth=None
    print(
        f"Building rota from {start_date.to_date_string()} to {end_date.to_date_string()}.."
    )

    rota_period = end_date - start_date
    rota_cycles = math.ceil(rota_period.days / 28)
    tasks = []
    j = 0
    if start_date == end_date:
        rota_cycles = 1
    async with aiohttp.ClientSession(
        auth=auth, cookies=cookies, connector=aiohttp.TCPConnector(limit=5)
    ) as session:
        for i in range(rota_cycles):
            if i == 0:
                tasks.append(
                    asyncio.create_task(
                        aget_rota(
                            session,
                            start_date.add(weeks=i * 4),
                            rota=None,
                            end=end_date,
                        )
                    )
                )
            else:  # subsequent rota start dates need to be start of week, or part of that week will get skipped
                tasks.append(
                    asyncio.create_task(
                        aget_rota(
                            session,
                            start_date.add(weeks=i * 4).start_of("week"),
                            rota=None,
                            end=end_date,
                        )
                    )
                )
        res = await asyncio.gather(*tasks)
    if res == [None]:
        return
    rota = [
        k for l in res for k in l
    ]  # List[List[shift]]->List[shift]    eg. [[shift,shift],[shift,shift,shift]] -> [shift, shift, shift]
    if queue:
        # with open("test_rota.json", "w") as f:
        #     for shift in rota:
        #         f.write(f"{shift.toJSON()},")
        queue.put(rota)
    return rota


async def aget_rota(session, date: pendulum.DateTime, rota=None, end=None):
    if not rota:
        rota = []
    start_date = date.start_of("week")
    if not end:
        end = start_date.add(days=27)
    end_date = min(start_date.add(days=27), end)
    period = pendulum.period(start_date, end_date)
    async with session.get(
        f"https://www.3r.org.uk/rota/for/{date.year}-{date.month}-{date.day}/month", allow_redirects=False
    ) as response:  # TypeError: post() takes 2 positional arguments but 3 were given
        print(
            f"Fetching rota for {start_date.to_date_string()} to {end_date.to_date_string()}.."
        )
        assert response
        html = await response.read()

    # print(res.status_code)

    soup = BeautifulSoup(html, "html.parser")

    for dt in period.range("days"):
        if dt < date:
            continue
        if end is not None and dt > end:
            break
        day = soup.find("td", id=f"day_{dt.format('YYYY_MM_DD')}")
        if not day:
            return
        shifts = day.find_all("div", class_="rota_item")

        for i in range(0, len(shifts), 2):

            time_element = shifts[i].find("div", class_="rota_item_time")
            time = time_element.text.strip()
            dt_obj = make_dt_obj(dt, time)
            detail = shifts[i].find("div", class_="rota_item_detail")
            persons = [person.text.strip() for person in detail.find_all("li")]
            shift_type = detail.find("div", class_="rota_item_time_name").text.strip()
            shift_id = shifts[i + 1]["data-shift-id"]

            vol_shift_id = shifts[i].find_all("li", class_="rota_shift_filled")
            vol_shift_id = [vs["data-volunteer-shift-id"] for vs in vol_shift_id]

            rota.append(
                RotaBro(
                    shift_id=shift_id,
                    date=dt.format("DD MMM YY"),
                    time=time,
                    type=shift_type,
                    vols=persons,
                    vol_shift_id=vol_shift_id,
                    dt_obj=dt_obj,
                )
            )
    return rota


def build_rota_data(
    session, start_date: pendulum.DateTime, end_date: pendulum.DateTime
):
    print(
        f"Building rota from {start_date.to_date_string()} to {end_date.to_date_string()}.."
    )
    rota = 0
    rota_period = end_date - start_date
    rota_cycles = math.ceil(rota_period.days / 28)
    if start_date == end_date:
        rota_cycles = 1
    for i in range(rota_cycles):
        rota = get_rota(session, start_date.add(weeks=i * 4), rota=rota, end=end_date)
    return rota


def get_rota(session, date: pendulum.DateTime, rota=None, end=None):
    if not rota:
        rota = []
    start_date = date.start_of("week")
    if not end:
        end = start_date.add(days=27)
    end_date = min(start_date.add(days=27), end)
    print(
        f"Fetching rota for {start_date.to_date_string()} to {end_date.to_date_string()}.."
    )
    period = pendulum.period(start_date, end_date)
    res = session.get(
        f"https://www.3r.org.uk/rota/for/{date.year}-{date.month}-{date.day}/month",
    )

    # print(res.status_code)

    soup = BeautifulSoup(res.content, "html.parser")

    for dt in period.range("days"):
        if dt < date:
            continue
        if end is not None and dt > end:
            break
        day = soup.find("td", id=f"day_{dt.format('YYYY_MM_DD')}")
        shifts = day.find_all("div", class_="rota_item")

        for i in range(0, len(shifts), 2):

            time_element = shifts[i].find("div", class_="rota_item_time")
            time = time_element.text.strip()
            dt_obj = make_dt_obj(dt, time)
            detail = shifts[i].find("div", class_="rota_item_detail")
            persons = [person.text.strip() for person in detail.find_all("li")]
            shift_type = detail.find("div", class_="rota_item_time_name").text.strip()
            shift_id = shifts[i + 1]["data-shift-id"]

            vol_shift_id = shifts[i].find_all("li", class_="rota_shift_filled")
            vol_shift_id = [vs["data-volunteer-shift-id"] for vs in vol_shift_id]

            rota.append(
                RotaBro(
                    shift_id=shift_id,
                    date=dt.format("DD MMM"),
                    time=time,
                    type=shift_type,
                    vols=persons,
                    vol_shift_id=vol_shift_id,
                    dt_obj=dt_obj,
                )
            )
    return rota


async def acreate_multiple_shifts(
    _session, time_list: List[pendulum.DateTime], shift_types: List[str]
):
    auth = aiohttp.BasicAuth(
        login=login_info["username"], password=login_info["password"], encoding="utf-8"
    )
    if shift_types == ["Both"]:
        shift_types = ["(Duty Room)", "(Leader)"]
    async with aiohttp.ClientSession(
        auth=auth, connector=aiohttp.TCPConnector(limit=5)
    ) as session:
        tasks = []
        res = []
        i = 0
        for times in time_list:
            for shift_type in shift_types:
                tasks.append(
                    asyncio.create_task(
                        acreate_shift(
                            session,
                            start_time=times[0],
                            end_time=times[1],
                            shift_type=shift_type,
                        )
                    )
                )
        for coro in asyncio.as_completed(tasks):
            res.append(await coro)
            # sg.one_line_progress_meter("Deleting Shifts", i + 1, len(tasks))
            i += 1
    #     responses = await asyncio.gather(*tasks)
    # print(responses)
    # sg.Popup(f"Shifts added: {responses}")
    # sg.Popup(f"Shifts added: {res}")
    return


async def acreate_shift(
    session,
    start_time: pendulum.DateTime,
    end_time: pendulum.DateTime,
    shift_type: str,
) -> str:
    start_str = start_time.format(
        "YYYY-MM-DD[T]HH:mm:ss[Z]"
    )  # time format: 2021-12-20T03:00:00Z
    end_str = end_time.format("YYYY-MM-DD[T]HH:mm:ss[Z]")
    print(
        f"Creating {shift_type} shift on {start_time.format('DD.MM.YY @ HHmm')}-{end_time.format('HHmm')}.."
    )
    form_data = {
        "shift[rota_id]": "",
        "shift[start_datetime]": start_str,
        "shift[all_day]": "0",
        "shift[end_datetime]": end_str,
        "shift[minimum_volunteers]": "",
        "shift[maximum_volunteers]": "",
        "shift[points]": "",
        "shift[recurrence_option]": "",
        "commit": "Create",
    }
    # for shift_type in shift_types:
    print(shift_type.lower())
    if shift_type.lower() == "(duty)" or shift_type.lower() == "(duty room)":
        form_data["shift[rota_id]"] = "204"
        form_data["shift[minimum_volunteers]"] = "2"
        form_data["shift[maximum_volunteers]"] = "2"
    elif shift_type.lower() == "(leader)":
        form_data["shift[rota_id]"] = "209"
        form_data["shift[minimum_volunteers]"] = "1"
        form_data["shift[maximum_volunteers]"] = "1"
    else:
        print(f"Shift type error: {shift_type}")
        raise TypeError
        # return

        # shift[rota_id]	"204"
        # shift[start_datetime]	"2022-12-27T00:00:00Z"
        # shift[all_day]	"0"
        # shift[end_datetime]	"2022-12-27T03:30:00Z"
        # shift[minimum_volunteers]	"2"
        # shift[maximum_volunteers]	"2"
        # shift[points]	""
        # shift[recurrence_option]	""
        # commit	"Create"

    async with session.post(
        "https://www.3r.org.uk/admin/shifts", data=form_data
    ) as response:  # TypeError: post() takes 2 positional arguments but 3 were given
        assert response
        tx = await response.read()
        with open("htmlres.html", "wb+") as f:
            f.write(tx)
        confirm = f"{shift_type} - {start_time.format('DD.MM.YY @ HHmm')}"
    return confirm


def create_multiple_shifts(
    session,
    time_list: List[List[pendulum.DateTime]],
    shift_types: List[str],
    window=None,
):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # if window:
    #     window.write_event_value("-CREATION STARTED-", "")
    for i, times in enumerate(time_list):
        # if not sg.one_line_progress_meter("Creating Shifts", i + 1, len(time_list)):
        #     break
        create_shift(
            session, start_time=times[0], end_time=times[1], shift_types=shift_types
        )
        # if window:
        #     window.write_event_value("-CREATION PROGRESS-", f"Creating shifts... {times[0].format('DD.MM.YY')}")
        # time.sleep(2)
        # window["-ADD TEXT-"].update(f"Creating shifts... {times[0].format('DD.MM.YY')}")
    # if window:
    #     window.write_event_value("-CREATION FINISHED-", "")
    return


def create_shift(
    session,
    start_time: pendulum.DateTime,
    end_time: pendulum.DateTime,
    shift_types: List[str],
):
    start_str = start_time.format(
        "YYYY-MM-DD[T]HH:mm:ss[Z]"
    )  # time format: 2021-12-20T03:00:00Z
    end_str = end_time.format("YYYY-MM-DD[T]HH:mm:ss[Z]")
    print(
        f"Creating {shift_types} shift on {start_time.format('DD.MM.YY @ HHmm')}-{end_time.format('HHmm')}.."
    )
    form_data = {
        "shift[rota_id]": "",
        "shift[start_datetime]": start_str,
        "shift[all_day]": "0",
        "shift[end_datetime]": end_str,
        "shift[minimum_volunteers]": "",
        "shift[maximum_volunteers]": "",
        "shift[points]": "",
        "shift[recurrence_option]": "",
        "commit": "Create",
    }
    for shift_type in shift_types:
        if shift_type.lower() == "(duty)" or shift_type.lower() == "(duty room)":
            form_data["shift[rota_id"] = "204"
            form_data["shift[minimum_volunteers]"] = "2"
            form_data["shift[maximum_volunteers]"] = "2"
        elif shift_type.lower() == "(leader)":
            form_data["shift[rota_id"] = "209"
            form_data["shift[minimum_volunteers]"] = "1"
            form_data["shift[maximum_volunteers]"] = "1"
        else:
            print(f"Shift type error: {shift_type}")
            raise TypeError
        r = session.post(f"https://www.3r.org.uk/admin/shifts", form_data)
        print(f"{shift_type} @ {start_time} , post = {r.ok}")
        return


async def adelete_all_shifts(
    _session,
    start_date: pendulum.datetime,
    end_date: pendulum.DateTime,
    types: List[str],
    empty_only: bool,
):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    print("aDeleting shifts")
    s = requests.Session()
    s.auth = (f'{login_info["username"]}', f'{login_info["password"]}')
    rota = await abuild_rota_data(s, start_date, end_date)
    print(rota)
    auth = aiohttp.BasicAuth(
        login=login_info["username"], password=login_info["password"], encoding="utf-8"
    )
    shifts_to_delete = []
    for shift in rota:
        shift.vols = [vol for vol in shift.vols if vol != "[sign up]"]
        if shift.type in types:
            if not empty_only or (empty_only and not shift.vols):
                shifts_to_delete.append(shift.shift_id)

    # if (
    #     sg.PopupOKCancel(
    #         f"Delete {len(shifts_to_delete)} shifts?\n\n{'ALL' if not empty_only else 'Empty'}, {types} shifts from:\n{start_date.format('dddd DD MMM YY')} to {end_date.format('dddd DD MMM YY')}"
    #     )
    #     != "OK"
    # ):
    #     return
    async with aiohttp.ClientSession(
        auth=auth, connector=aiohttp.TCPConnector(limit=5)
    ) as session:
        tasks = []
        res = []
        i = 0
        for id in shifts_to_delete:
            tasks.append(asyncio.create_task(adelete_shift(session, id)))
        for coro in asyncio.as_completed(tasks):
            res.append(await coro)
            # sg.one_line_progress_meter("Deleting Shifts", i + 1, len(tasks))
            # i += 1
        # r = await asyncio.gather(*tasks)
    # print(f"{len(r)} shifts deleted")
    # sg.Popup(f"{len(r)} shifts deleted")
    # sg.Popup(f"{len(res)} shifts deleted")
    return


async def adelete_shift(session, shift_id: str) -> str:
    async with session.post(
        f"https://www.3r.org.uk/rota/delete/{shift_id}"
    ) as response:
        assert response
        await response.read()
    return f"{shift_id} deleted"


def delete_all_shifts(
    session,
    start_date: pendulum.datetime,
    end_date: pendulum.DateTime,
    types: List[str],
    empty_only: bool,
):
    rota = build_rota_data(session, start_date, end_date)
    shifts_to_delete = []
    for shift in rota:
        shift.vols = [vol for vol in shift.vols if shift.vols == "[sign up]"]
        if shift.type in types:
            print(f"type: {shift.type}, vols: {shift.vols}")
            if not empty_only or (empty_only and not shift.vols):
                shifts_to_delete.append(shift.shift_id)
    print("Deleting shifts..")
    for i, id in enumerate(shifts_to_delete):
        # if not sg.one_line_progress_meter(
        #     "Deleting Shifts", i + 1, len(shifts_to_delete), orientation="h"
        # ):
        #     break
        delete_shift(session, id)
    print(f"{len(shifts_to_delete)} shifts deleted")


def delete_shift(session, shift_id):
    # session.requests.Request("POST", f"https://www.3r.org.uk/rota/delete/{shift_id}")
    r = session.post(f"https://www.3r.org.uk/rota/delete/{shift_id}")
    return
    ...  # post to https://www.3r.org.uk/rota/delete/57940346  <div id="shift_57940346" class="rota_item ..." data-shift-id="57940346"


if __name__ == "__main__":
    s = requests.Session()
    s.auth = (f'{login_info["username"]}', f'{login_info["password"]}')
    print(get_vol_shifts_by_name(s, "Ramon 957"))

    # # async rota gives same response as normal rota
    # td = pendulum.today()
    # nstart = time.time()
    # srota = build_rota_data(s, td, td.add(months=2))
    # nend = time.time()

    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # astart = time.time()
    # arota = asyncio.run(abuild_rota_data("c", td, td.add(months=2)))
    # aend = time.time()
    # assert srota == arota
    # print(f"Normal fetch: {nend-nstart}, Async fetch: {aend-astart}")

    # start = "20.12.2021 03:00"
    # start_dt = pendulum.from_format(start, "DD.MM.YYYY HH:mm")
    # end = "20.12.2021 05:00"
    # end_dt = pendulum.from_format(end, "DD.MM.YYYY HH:mm")

    # types = ["Duty", "Leader"]
    # create_shift(s, start_dt, end_dt, types)

    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # asyncio.run(post_all_sign_ups(1,2,3))
    # make_sign_ups(s)

    # date = pendulum.today()
    # pattern = [
    #     ["Monday 19:00-22:00", "Tuesday 19:00-22:00"],
    #     ["OFF"],
    #     ["OFF"],
    #     ["OFF"],
    #     ["Thursday 22:30-01:00"],
    #     ["Thursday 19:00-22:00"],
    #     ["Wednesday 19:00-22:00"],
    #     ["Friday 19:00-22:00"],
    # ]
    # dates = pattern_to_dates(s, pattern)

    # print(f"Number of shifts: {len(dates)}\n{dates}")
    # rota = build_rota_data(s, date, date.add(months=2))

    # for shift in rota:
    #     print(f"id: {shift.shift_id}, date: {shift.date} {shift.time}")
    # print(len(rota))
    # print(get_week_number(s, date.add(weeks=2)))

    # rota = get_rota(s, date)
    # exp, skip = dates_to_shift_ids(dates, rota)

    # vol = get_vol_by_name(s, "Natashaj 1928")
    # print(vol.id, type(vol.id))

    # verify_shify_ready_for_signup(vol, exp)

    # rota = get_rota(s, date.add(weeks=4), rota)
    # rota = get_rota(s, date.add(weeks=8), rota)
    # for shift in rota:
    #     print(f"{shift.date} - {shift.time}")
    # print(get_rota(s, date))
    # get_vol_shifts_by_name(s, "Ramon 957")

    # data = {"vol_id": "67048", "shift_id": "54995305"}
    # post_sign_up(s, data)
    # get_active_volunteers(s)
