import unittest
from booking_input import patient_datetime


class BookingInputTests(unittest.TestCase):
    def test_customer_real_message_with_space_before_slash(self):
        self.assertEqual(patient_datetime('pode ser dia 12 /11/2026 as 8:30'),'12/11/2026 08:30')
        self.assertEqual(patient_datetime('12 / 11 / 2026 as 08:30'),'12/11/2026 08:30')
        self.assertEqual(patient_datetime('dia 12/11/2026 as 8 horas'),'12/11/2026 08:00')

    def test_multiple_slots_are_not_silently_reduced_to_first(self):
        with self.assertRaisesRegex(ValueError,'vários horários'):
            patient_datetime('2026-11-17: 08:00, 08:30, 09:00, 09:30, 10:00')
        self.assertEqual(patient_datetime('2026-11-17: 08:30'),'2026-11-17 08:30')

    def test_invalid_or_partial_dates_and_times_do_not_become_other_dates(self):
        for text in ['11/2026 as 8:30','31/02/2026 as 8h','12/13/2026 as 8h','12/11/2026 as 25:30']:
            with self.assertRaises(ValueError,msg=text):patient_datetime(text)
        with self.assertRaises(ValueError):patient_datetime('12/11/2026 ou 13/11/2026 as 8h')

    def test_relative_date_and_single_slot(self):
        self.assertEqual(patient_datetime('amanha as 8h30'),'amanha 08:30')
        self.assertEqual(patient_datetime('depois de amanha as 8'),'depois de amanha 08:00')
        self.assertEqual(patient_datetime('e sexta as 10 da manha'), 'sexta 10:00')
        self.assertEqual(patient_datetime('na proxima terca-feira as 3 da tarde'), 'proxima terca-feira 15:00')
