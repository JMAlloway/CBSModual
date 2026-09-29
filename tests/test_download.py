from bankscreener.download import _date_select, _download_button, _parse, _product_select
from bankscreener.quarters import Quarter

PAGE = """
<form action="./DownloadBulkData.aspx" method="post">
<input type="hidden" name="__VIEWSTATE" value="abc" />
<select name="ctl00$Main$ListBox1">
  <option value="ReportingSeriesSinglePeriod">Call Reports -- Single Period</option>
  <option value="PerformanceReportingSeriesSinglePeriod">UBPR Ratio -- Single Period</option>
</select>
<select name="ctl00$Main$DatesDropDownList">
  <option selected="selected" value="160">06/30/2024</option>
  <option value="159">03/31/2024</option>
</select>
<input type="radio" name="ctl00$Main$FormatType" value="TSVRadioButton" />
<input type="submit" name="ctl00$Main$Download_0" value="Download" />
</form>
"""


def test_form_parsing():
    form = _parse(PAGE)
    assert _product_select(form, "UBPR Ratio -- Single Period") == (
        "ctl00$Main$ListBox1", "PerformanceReportingSeriesSinglePeriod")
    name, dates = _date_select(form)
    assert name == "ctl00$Main$DatesDropDownList"
    assert dates == {Quarter(2024, 2): "160", Quarter(2024, 1): "159"}
    assert _download_button(form) == ("ctl00$Main$Download_0", "Download")
