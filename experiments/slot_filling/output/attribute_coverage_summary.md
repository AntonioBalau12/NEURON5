# Attribute coverage summary (dev only; CV = out-of-fold)

Lexicon attributes: 321. Detail: `attribute_coverage.csv`.

| status | attributes |
|---|---|
| extracted_but_none_correct_cv | 11 |
| no_dev_gold | 3 |
| ok | 221 |
| zero_extraction_cv | 86 |

Attributes with dev gold: 318. Recall buckets (CV): 0.5<=recall<0.9: 99, 0<recall<0.5: 49, recall=0: 97, recall>=0.9: 73

No dev gold (3): ai_editing, livestreamed, newsletter_subscribers

Dev gold but zero extraction in CV (86): ad_free_option, adaptive_noise_cancelling, anonymous, applicants, appointment_booking, archive_storage_price, audit_committee, beta_opened, bike_racks, call_length, camera_translation, caption_languages, cellular_option, chair_since, chairs, cloud_recording, cool_storage_price, copilot_included, cost_per_hire, cycling_commuters, desktop_mode, devices_keynote_speaker, devices_recycled, duration, emissions_cut_target, executive_owner, executive_sponsor, externally_audited, family_group_size, features_launched, first_reply, footprint, gemini_formula_assist, growth_opportunities, guidance, had_major_outage, head_of_workspace, headcount, hires, interview_rounds, keynote_length, keynote_speaker, latest_release_date, manager_rating, manufacturing_partner, max_call_length, max_guests, maximum_seats, median_time_to_recover, minimum_nodes, newest_region, offer_acceptance, offline_maps, on_device_gemini, open_for, opened, opening_keynote, owner, p99_response_time, personalised_ads_by_default, previous_employer, pro_price, pro_tier, recruiters, referral_bonus, referral_share, refresh_rate, renewable_electricity, rent, replay_available, revenue_growth, run_by, satellite_messaging, series_a_co_investor, shipping_android, speakers, stable_release, stable_release_date, stream_viewers, training_data_cutoff, travel_emissions_cut, venue, voice_guidance_languages, webcast_viewers, workshops, would_recommend

Extracted but none correct in CV (11): annual_recurring_revenue, chairs_audit_committee, customers_in_the_eu, encryption_at_rest, extra_seat_price, host, independent_director, open_engineering_roles, raised_series_a, raised_series_b, trade_in_programme

Attributes with zero facts in the frozen output over all input rows: 54

## Per value kind (CV, out-of-fold)

| kind | dev gold | named in text | predicted | correct | wrong value | extra | precision | recall |
|---|---|---|---|---|---|---|---|---|
| quantity | 885 | 614 | 607 | 591 | 2 | 14 | 0.974 | 0.668 |
| money | 224 | 157 | 118 | 114 | 0 | 4 | 0.966 | 0.509 |
| percent | 177 | 84 | 81 | 81 | 0 | 0 | 1.0 | 0.458 |
| duration | 199 | 125 | 113 | 111 | 1 | 1 | 0.982 | 0.558 |
| date | 144 | 107 | 71 | 68 | 0 | 3 | 0.958 | 0.472 |
| version | 110 | 108 | 108 | 104 | 0 | 4 | 0.963 | 0.945 |
| name | 183 | 104 | 56 | 47 | 1 | 8 | 0.839 | 0.257 |
| boolean | 148 | 120 | 85 | 77 | 0 | 8 | 0.906 | 0.52 |

## Per value kind (frozen output on dev rows, IN-SAMPLE: optimistic)

| kind | dev gold | predicted | correct | wrong value | extra | precision | recall |
|---|---|---|---|---|---|---|---|
| quantity | 885 | 607 | 594 | 6 | 7 | 0.979 | 0.671 |
| money | 224 | 156 | 152 | 0 | 4 | 0.974 | 0.679 |
| percent | 177 | 84 | 84 | 0 | 0 | 1.0 | 0.475 |
| duration | 199 | 123 | 122 | 0 | 1 | 0.992 | 0.613 |
| date | 144 | 95 | 89 | 0 | 6 | 0.937 | 0.618 |
| version | 110 | 108 | 106 | 0 | 2 | 0.981 | 0.964 |
| name | 183 | 95 | 77 | 10 | 8 | 0.811 | 0.421 |
| boolean | 148 | 118 | 110 | 0 | 8 | 0.932 | 0.743 |
