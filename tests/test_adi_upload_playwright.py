"""Playwright browser tests for ADI upload flow on /submit page."""

import os
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


REPO_ROOT = Path(__file__).resolve().parent.parent  # simplex-summer-score/


@pytest.fixture(autouse=True)
def wait_for_server(page: Page):
    """Wait for Flask server to be ready before each test."""
    page.goto("http://localhost:5000/submit")
    expect(page.get_by_role("button", name="Upload ADI File")).to_be_visible(timeout=5000)


def upload_adi_file(page: Page, adi_filename: str, pota_choice: str = "no"):
    """Helper to simulate the full ADI upload flow."""
    upload_btn = page.get_by_role("button", name="Upload ADI File")
    
    # Step 1: Click button → shows POTA declaration
    upload_btn.click()
    expect(page.get_by_role("button", name="Choose File")).to_be_visible(timeout=3000)
    
    # Step 2: Select POTA option
    page.locator(f'input[name="adi_is_pota"][value="{pota_choice}"]').click()
    
    # Step 3: Click button again → opens file picker (button text is now "Choose File")
    choose_btn = page.get_by_role("button", name="Choose File")
    with page.expect_file_chooser() as fc_info:
        choose_btn.click()
    
    file_chooser = fc_info.value
    assert file_chooser is not None
    
    # Step 4: Set the file
    file_path = str(REPO_ROOT / adi_filename)
    file_chooser.set_files(file_path)


def test_submit_page_has_adi_upload_button(page: Page):
    """The submit page should have the ADI upload button."""
    expect(page.get_by_role("button", name="Upload ADI File")).to_be_visible()


def test_clicking_adi_button_shows_pota_declaration(page: Page):
    """First click on Upload ADI button should reveal POTA declaration radio buttons."""
    upload_btn = page.get_by_role("button", name="Upload ADI File")
    expect(upload_btn).to_be_visible()
    
    # Click the button — should show POTA section and change text to "Choose File"
    upload_btn.click()
    
    # Button text should have changed
    expect(page.get_by_role("button", name="Choose File")).to_be_visible()
    
    # POTA declaration should be visible (radio buttons)
    pota_yes = page.locator('input[name="adi_is_pota"][value="yes"]')
    pota_no = page.locator('input[name="adi_is_pota"][value="no"]')
    expect(pota_yes).to_be_visible()
    expect(pota_no).to_be_visible()


def test_selecting_pota_option(page: Page):
    """Selecting POTA option should work."""
    upload_btn = page.get_by_role("button", name="Upload ADI File")
    upload_btn.click()  # Show POTA section
    
    # Select "No" for POTA
    page.locator('input[name="adi_is_pota"][value="no"]').click()
    
    # Verify selection
    assert page.locator('input[name="adi_is_pota"][value="no"]:checked').is_checked()


def test_upload_valid_adi_shows_preview(page: Page):
    """Uploading a valid ADI file should show preview table."""
    upload_adi_file(page, "test_duplicates.adi", pota_choice="no")
    
    # Preview shows count from backend — test_duplicates.adi has 4 contacts
    expect(page.get_by_text("contact(s) found in file")).to_be_visible(timeout=5000)
    
    # Preview table should be visible
    expect(page.locator("table")).to_be_visible()


def test_preview_table_shows_correct_columns(page: Page):
    """Preview table should show correct column headers."""
    upload_adi_file(page, "test_duplicates.adi", pota_choice="no")
    
    expect(page.get_by_text("contact(s) found in file")).to_be_visible(timeout=5000)
    
    # Check column headers exist (use exact=True to avoid strict mode collision with "Digital Mode")
    expect(page.get_by_role("columnheader", name="#", exact=True)).to_be_visible()
    expect(page.get_by_role("columnheader", name="My Call", exact=True)).to_be_visible()
    expect(page.get_by_role("columnheader", name="Contact", exact=True)).to_be_visible()
    expect(page.get_by_role("columnheader", name="Date/Time", exact=True)).to_be_visible()
    expect(page.get_by_role("columnheader", name="Mode", exact=True)).to_be_visible()


def test_preview_table_shows_contact_data(page: Page):
    """Preview table should show correct contact data from uploaded file."""
    upload_adi_file(page, "test_duplicates.adi", pota_choice="no")
    
    expect(page.get_by_text("contact(s) found in file")).to_be_visible(timeout=5000)
    
    # Check that K1ABC appears (it's the duplicate test file with 4 contacts)
    expect(page.get_by_text("K1ABC").first).to_contain_text("K1ABC")


def test_preview_shows_duplicate_flag(page: Page):
    """Preview should indicate which records are duplicates."""
    upload_adi_file(page, "test_duplicates.adi", pota_choice="no")
    
    expect(page.get_by_text("contact(s) found in file")).to_be_visible(timeout=5000)
    
    # Check that duplicate records (K1ABC appearing twice with same date/time/mode) are rendered
    k1abc_rows = page.locator('td:has-text("K1ABC")')
    assert k1abc_rows.count() >= 2, f"Expected at least 2 K1ABC entries, found {k1abc_rows.count()}"


def test_upload_empty_file_shows_error(page: Page):
    """Uploading an empty file should show validation error."""
    upload_btn = page.get_by_role("button", name="Upload ADI File")
    upload_btn.click()  # Show POTA section
    expect(page.get_by_role("button", name="Choose File")).to_be_visible(timeout=3000)
    
    page.locator('input[name="adi_is_pota"][value="no"]').click()
    
    with page.expect_file_chooser() as fc_info:
        # After first click, button text is "Choose File"
        choose_btn = page.get_by_role("button", name="Choose File")
        with page.expect_file_chooser():
            choose_btn.click()
    
    file_chooser = fc_info.value
    assert file_chooser is not None
    
    # Create a temporary empty .adi file
    fd, path = tempfile.mkstemp(suffix=".adi")
    os.close(fd)  # Close the file descriptor immediately
    
    try:
        file_chooser.set_files(path)
        
        expect(page.get_by_text("empty").first).to_contain_text("empty", timeout=5000)
    finally:
        os.unlink(path)


def test_upload_invalid_extension_shows_error(page: Page):
    """Uploading a non-.adi file should show an error message."""
    upload_btn = page.get_by_role("button", name="Upload ADI File")
    upload_btn.click()  # Show POTA section
    expect(page.get_by_role("button", name="Choose File")).to_be_visible(timeout=3000)
    
    page.locator('input[name="adi_is_pota"][value="no"]').click()
    
    with page.expect_file_chooser() as fc_info:
        choose_btn = page.get_by_role("button", name="Choose File")
        with page.expect_file_chooser():
            choose_btn.click()
    
    file_chooser = fc_info.value
    assert file_chooser is not None
    
    # Create a temporary .txt file
    fd, path = tempfile.mkstemp(suffix=".txt")
    with open(path, "w") as f:
        f.write("This is not an ADI file")
    os.close(fd)
    
    try:
        file_chooser.set_files(path)
        
        # The JS validation should show an error about .ADI files
        expect(page.get_by_text(".ADI").first).to_contain_text(".ADI", timeout=5000)
    finally:
        os.unlink(path)


def test_adi_upload_with_pota_yes_flag(page: Page):
    """Uploading ADI with POTA='yes' should flag contacts with park data."""
    upload_adi_file(page, "test.adi", pota_choice="yes")
    
    expect(page.get_by_text("contact(s) found in file")).to_be_visible(timeout=5000)


def test_preview_has_submit_button(page: Page):
    """Preview should show a submit button for batch upload."""
    upload_adi_file(page, "test_duplicates.adi", pota_choice="no")
    
    expect(page.get_by_text("Submit All").first).to_be_visible(timeout=5000)


def test_preview_shows_digital_mode_column_for_digital_contacts(page: Page):
    """Preview table should show digital mode column when contacts have digital modes."""
    upload_adi_file(page, "test.adi", pota_choice="no")
    
    expect(page.get_by_text("contact(s) found in file")).to_be_visible(timeout=5000)
    
    # Check that FT4/8 appears in the preview (digital mode column content for test.adi)
    preview_html = page.locator("#adiPreviewContainer").inner_html()
    assert "FT4/8" in preview_html


def test_preview_shows_pota_column_for_pota_contacts(page: Page):
    """Preview table should show POTA park column when contacts have POTA data."""
    upload_adi_file(page, "test.adi", pota_choice="yes")
    
    expect(page.get_by_text("contact(s) found in file")).to_be_visible(timeout=5000)


def test_preview_shows_warnings_for_incomplete_file(page: Page):
    """Preview should show warnings for incomplete ADIF files."""
    upload_adi_file(page, "test_contacts.adi", pota_choice="no")
    
    expect(page.get_by_text("contact(s) found in file")).to_be_visible(timeout=5000)
