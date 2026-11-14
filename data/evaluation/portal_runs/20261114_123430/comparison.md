# Portal runs compared: 20261113_223410 → 20261114_123430

First answer: correct + confidently wrong + asks = 100% per row. After 1 answer: the simulated patient answered the body-area question once (favourable by construction: the answer comes from the expected speciality). Rule labels: draft, not yet doctor-reviewed (gretel only; core50 and mediroute unchanged).

## Current gold labels

| Set | Run | Correct | Confidently wrong | Asks | After 1 answer: correct | still wrong | still open |
|---|---|---|---|---|---|---|---|
| core50 (n=50) | before | 90% (45) | 0% (0) | 10% (5) | 90% (45) | 0% (0) | 10% (5) |
| core50 (n=50) | after | 88% (44) | 0% (0) | 12% (6) | 100% (50) | 0% (0) | 0% (0) |
| mediroute (n=84) | before | 94% (79) | 1% (1) | 5% (4) | 94% (79) | 1% (1) | 5% (4) |
| mediroute (n=84) | after | 94% (79) | 0% (0) | 6% (5) | 100% (84) | 0% (0) | 0% (0) |
| gretel (n=100) | before | 56% (56) | 18% (18) | 26% (26) | 56% (56) | 18% (18) | 26% (26) |
| gretel (n=100) | after | 31% (31) | 15% (15) | 54% (54) | 79% (79) | 18% (18) | 3% (3) |
| all (n=234) | before | 77% (180) | 8% (19) | 15% (35) | 77% (180) | 8% (19) | 15% (35) |
| all (n=234) | after | 66% (154) | 6% (15) | 28% (65) | 91% (213) | 8% (18) | 1% (3) |

## Gretel rule labels (draft)

| Set | Run | Correct | Confidently wrong | Asks | After 1 answer: correct | still wrong | still open |
|---|---|---|---|---|---|---|---|
| core50 (n=50) | before | 90% (45) | 0% (0) | 10% (5) | 90% (45) | 0% (0) | 10% (5) |
| core50 (n=50) | after | 88% (44) | 0% (0) | 12% (6) | 100% (50) | 0% (0) | 0% (0) |
| mediroute (n=84) | before | 94% (79) | 1% (1) | 5% (4) | 94% (79) | 1% (1) | 5% (4) |
| mediroute (n=84) | after | 94% (79) | 0% (0) | 6% (5) | 100% (84) | 0% (0) | 0% (0) |
| gretel (n=100) | before | 53% (53) | 21% (21) | 26% (26) | 53% (53) | 21% (21) | 26% (26) |
| gretel (n=100) | after | 44% (44) | 2% (2) | 54% (54) | 96% (96) | 2% (2) | 2% (2) |
| all (n=234) | before | 76% (177) | 9% (22) | 15% (35) | 76% (177) | 9% (22) | 15% (35) |
| all (n=234) | after | 71% (167) | 1% (2) | 28% (65) | 98% (230) | 1% (2) | 1% (2) |
