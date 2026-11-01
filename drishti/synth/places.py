"""Localities of the 24 cities in the synthetic world, with approximate coordinates (public geography).

Cell sites, ANPR cameras, police stations, FIRs, business addresses and properties are placed around these
so that a label ("Hadapsar") and a point on the map agree. Coordinates are approximate (within a kilometre
or two); nothing here describes a real person.
"""

from __future__ import annotations

LOCALITIES: dict[str, list[tuple[str, float, float]]] = {
    "Mumbai": [("Colaba", 18.910, 72.820), ("Fort", 18.935, 72.835), ("Byculla", 18.980, 72.830), ("Dadar", 19.020, 72.840),
               ("Worli", 19.010, 72.815), ("Parel", 19.000, 72.840), ("Mahim", 19.040, 72.840), ("Bandra", 19.060, 72.840),
               ("Kurla", 19.070, 72.880), ("Ghatkopar", 19.086, 72.910), ("Chembur", 19.060, 72.900), ("Dharavi", 19.040, 72.855),
               ("Sion", 19.040, 72.860), ("Malabar Hill", 18.955, 72.800), ("Tardeo", 18.970, 72.810), ("Wadala", 19.020, 72.870)],
    "Andheri": [("Andheri East", 19.115, 72.870), ("Andheri West", 19.136, 72.830), ("Jogeshwari", 19.140, 72.850), ("Vile Parle", 19.100, 72.850),
                ("Marol", 19.120, 72.880), ("Versova", 19.130, 72.810), ("Goregaon", 19.165, 72.850), ("Powai", 19.120, 72.905),
                ("Malad", 19.186, 72.848), ("Santacruz", 19.080, 72.840)],
    "Thane": [("Naupada", 19.190, 72.975), ("Wagle Estate", 19.205, 72.955), ("Kalwa", 19.200, 73.000), ("Mumbra", 19.180, 73.020),
              ("Kopri", 19.180, 72.980), ("Majiwada", 19.215, 72.985), ("Ghodbunder Road", 19.250, 72.970), ("Vartak Nagar", 19.210, 72.965),
              ("Kasarvadavali", 19.260, 72.970), ("Lokmanya Nagar", 19.200, 72.950)],
    "Navi Mumbai": [("Vashi", 19.077, 72.998), ("Sanpada", 19.060, 73.010), ("Nerul", 19.033, 73.018), ("Belapur", 19.020, 73.040),
                    ("Kharghar", 19.030, 73.070), ("Airoli", 19.157, 72.995), ("Ghansoli", 19.120, 73.000), ("Koparkhairane", 19.100, 73.010),
                    ("Turbhe", 19.070, 73.020), ("Seawoods", 19.020, 73.020)],
    "Pune": [("Hadapsar", 18.500, 73.930), ("Kondhwa", 18.470, 73.890), ("Kothrud", 18.500, 73.810), ("Shivajinagar", 18.530, 73.850),
             ("Deccan", 18.517, 73.840), ("Wakad", 18.600, 73.760), ("Hinjewadi", 18.590, 73.740), ("Yerawada", 18.550, 73.890),
             ("Viman Nagar", 18.567, 73.915), ("Swargate", 18.500, 73.860), ("Katraj", 18.450, 73.860), ("Aundh", 18.560, 73.810),
             ("Baner", 18.560, 73.790), ("Kharadi", 18.550, 73.940), ("Warje", 18.480, 73.800), ("Bibwewadi", 18.470, 73.860),
             ("Pimpri", 18.630, 73.800), ("Chinchwad", 18.650, 73.790), ("Bhosari", 18.620, 73.850), ("Camp", 18.515, 73.880)],
    "Nagpur": [("Sitabuldi", 21.145, 79.085), ("Dharampeth", 21.140, 79.070), ("Sadar", 21.160, 79.080), ("Ajni", 21.120, 79.090),
               ("Kotwali", 21.150, 79.110), ("Manish Nagar", 21.090, 79.080), ("Wardhaman Nagar", 21.150, 79.130), ("Jaripatka", 21.180, 79.100),
               ("Pratap Nagar", 21.120, 79.050), ("Hingna Road", 21.110, 79.030), ("Gittikhadan", 21.170, 79.060), ("Nandanvan", 21.130, 79.130)],
    "Nashik": [("Panchavati", 20.010, 73.790), ("Sarkarwada", 20.000, 73.790), ("Gangapur Road", 20.010, 73.760), ("Satpur", 20.000, 73.740),
               ("Ambad", 19.960, 73.740), ("Nashik Road", 19.950, 73.840), ("Indira Nagar", 19.970, 73.780), ("Cidco", 19.970, 73.760),
               ("Mumbai Naka", 19.990, 73.780), ("Adgaon", 20.030, 73.830)],
    "Kolhapur": [("Rajarampuri", 16.690, 74.250), ("Shahupuri", 16.705, 74.240), ("Laxmipuri", 16.700, 74.230), ("Juna Rajwada", 16.695, 74.225),
                 ("Kasba Bawda", 16.730, 74.240), ("Gandhinagar", 16.710, 74.290), ("Shivaji Peth", 16.690, 74.220), ("Ruikar Colony", 16.700, 74.260)],
    "Solapur": [("Sadar Bazar", 17.670, 75.910), ("Murarji Peth", 17.670, 75.900), ("Jodbhavi Peth", 17.680, 75.910), ("Vijapur Road", 17.650, 75.900),
                ("Akkalkot Road MIDC", 17.650, 75.930), ("Faujdar Chawdi", 17.675, 75.905), ("Hotgi Road", 17.640, 75.920), ("Saat Rasta", 17.665, 75.910)],
    "Aurangabad": [("CIDCO", 19.880, 75.370), ("Kranti Chowk", 19.870, 75.330), ("Osmanpura", 19.865, 75.320), ("Begumpura", 19.900, 75.310),
                   ("Jinsi", 19.890, 75.330), ("Waluj", 19.840, 75.230), ("Cantonment", 19.870, 75.300), ("Mukundwadi", 19.880, 75.380),
                   ("Satara Parisar", 19.840, 75.330)],
    "Bhiwandi": [("Narpoli", 19.290, 73.050), ("Shanti Nagar", 19.300, 73.070), ("Nizampura", 19.295, 73.065), ("Bhoiwada", 19.300, 73.060),
                 ("Kongaon", 19.280, 73.080)],
    "Panvel": [("Panvel City", 18.990, 73.115), ("Kamothe", 19.020, 73.100), ("Kalamboli", 19.030, 73.100), ("New Panvel", 18.995, 73.125),
               ("Khanda Colony", 19.000, 73.120), ("Taloja", 19.060, 73.120)],
    "Surat": [("Adajan", 21.190, 72.790), ("Varachha", 21.210, 72.860), ("Athwa", 21.180, 72.810), ("Udhna", 21.170, 72.840),
              ("Katargam", 21.230, 72.830), ("Vesu", 21.140, 72.780), ("Rander", 21.220, 72.800), ("Limbayat", 21.180, 72.860), ("Puna", 21.200, 72.880)],
    "Ahmedabad": [("Navrangpura", 23.040, 72.560), ("Maninagar", 22.995, 72.600), ("Satellite", 23.030, 72.520), ("Vastrapur", 23.040, 72.530),
                  ("Bopal", 23.030, 72.470), ("Naroda", 23.070, 72.660), ("Chandkheda", 23.110, 72.585), ("Paldi", 23.010, 72.560),
                  ("Sabarmati", 23.080, 72.580), ("Vatva", 22.960, 72.620)],
    "New Delhi": [("Connaught Place", 28.630, 77.220), ("Karol Bagh", 28.650, 77.190), ("Lajpat Nagar", 28.570, 77.240), ("Saket", 28.520, 77.210),
                  ("Dwarka", 28.590, 77.050), ("Rohini", 28.740, 77.070), ("Chandni Chowk", 28.655, 77.230), ("Janakpuri", 28.620, 77.080),
                  ("Mayur Vihar", 28.610, 77.290), ("Vasant Kunj", 28.525, 77.160), ("Paharganj", 28.645, 77.210), ("Okhla", 28.530, 77.270)],
    "Hyderabad": [("Banjara Hills", 17.415, 78.440), ("Jubilee Hills", 17.430, 78.410), ("Gachibowli", 17.440, 78.350), ("Secunderabad", 17.440, 78.500),
                  ("Kukatpally", 17.490, 78.400), ("Charminar", 17.360, 78.470), ("Ameerpet", 17.435, 78.445), ("Madhapur", 17.450, 78.390),
                  ("LB Nagar", 17.350, 78.550), ("Begumpet", 17.440, 78.470), ("Mehdipatnam", 17.395, 78.430)],
    "Bengaluru": [("Koramangala", 12.935, 77.620), ("Indiranagar", 12.970, 77.640), ("Whitefield", 12.970, 77.750), ("Jayanagar", 12.930, 77.580),
                  ("Malleshwaram", 13.000, 77.570), ("Hebbal", 13.035, 77.590), ("Electronic City", 12.845, 77.660), ("HSR Layout", 12.910, 77.640),
                  ("BTM Layout", 12.915, 77.610), ("Yelahanka", 13.100, 77.595), ("Rajajinagar", 12.990, 77.550), ("Majestic", 12.977, 77.570)],
    "Kolkata": [("Park Street", 22.550, 88.350), ("Salt Lake", 22.580, 88.410), ("Howrah", 22.590, 88.310), ("Behala", 22.500, 88.310),
                ("Dum Dum", 22.620, 88.420), ("Ballygunge", 22.530, 88.365), ("Garia", 22.465, 88.390), ("New Town", 22.580, 88.460),
                ("Shyambazar", 22.600, 88.370), ("Esplanade", 22.565, 88.350)],
    "Jaipur": [("Malviya Nagar", 26.855, 75.810), ("Vaishali Nagar", 26.910, 75.740), ("Mansarovar", 26.860, 75.760), ("C-Scheme", 26.910, 75.800),
               ("Raja Park", 26.900, 75.830), ("Sanganer", 26.820, 75.790), ("Johari Bazar", 26.920, 75.830), ("Jhotwara", 26.950, 75.740),
               ("Tonk Road", 26.870, 75.800)],
    "Lucknow": [("Hazratganj", 26.850, 80.945), ("Gomti Nagar", 26.860, 81.000), ("Aliganj", 26.890, 80.940), ("Indira Nagar", 26.880, 80.990),
                ("Alambagh", 26.810, 80.900), ("Charbagh", 26.830, 80.920), ("Aminabad", 26.845, 80.925), ("Chowk", 26.870, 80.910),
                ("Mahanagar", 26.875, 80.955)],
    "Indore": [("Vijay Nagar", 22.750, 75.895), ("Palasia", 22.725, 75.885), ("Rajwada", 22.718, 75.855), ("Bhawarkua", 22.690, 75.865),
               ("Sudama Nagar", 22.700, 75.830), ("Khajrana", 22.740, 75.920), ("Sapna Sangeeta", 22.700, 75.870), ("Rau", 22.640, 75.810)],
    "Panaji": [("Miramar", 15.480, 73.810), ("Altinho", 15.495, 73.830), ("Campal", 15.490, 73.820), ("Patto", 15.495, 73.835),
               ("Ribandar", 15.500, 73.860), ("Dona Paula", 15.460, 73.800), ("Taleigao", 15.470, 73.820), ("Porvorim", 15.530, 73.820)],
    "Chennai": [("T Nagar", 13.040, 80.235), ("Adyar", 13.005, 80.255), ("Anna Nagar", 13.085, 80.210), ("Velachery", 12.980, 80.220),
                ("Mylapore", 13.035, 80.270), ("Guindy", 13.010, 80.210), ("Egmore", 13.075, 80.260), ("Tambaram", 12.925, 80.120),
                ("Royapettah", 13.055, 80.265), ("Perambur", 13.110, 80.240)],
    "Kochi": [("Edappally", 10.025, 76.310), ("Kakkanad", 10.015, 76.345), ("Fort Kochi", 9.965, 76.240), ("Vyttila", 9.970, 76.320),
              ("Kaloor", 9.995, 76.290), ("Ernakulam South", 9.970, 76.290), ("Palarivattom", 10.005, 76.310), ("Kadavanthra", 9.970, 76.300),
              ("Thrikkakara", 10.030, 76.330)],
}

# FIR prefixes: state and commissionerate codes as they appear in FIR numbers
FIR_UNIT = {"Mumbai": "MUM", "Andheri": "MUM", "Thane": "THN", "Navi Mumbai": "NMB", "Pune": "PUNE", "Nagpur": "NGP", "Nashik": "NSK",
            "Kolhapur": "KOP", "Solapur": "SLP", "Aurangabad": "AUR", "Bhiwandi": "THN", "Panvel": "NMB", "Surat": "SRT", "Ahmedabad": "AHD",
            "New Delhi": "DEL", "Hyderabad": "HYD", "Bengaluru": "BLR", "Kolkata": "KOL", "Jaipur": "JPR", "Lucknow": "LKO", "Indore": "IDR",
            "Panaji": "PNJ", "Chennai": "CHN", "Kochi": "KOC"}

# registering authority (RTO) series for vehicles of each city
RTO = {"Mumbai": "MH01", "Andheri": "MH02", "Thane": "MH04", "Navi Mumbai": "MH43", "Pune": "MH12", "Nagpur": "MH31", "Nashik": "MH15",
       "Kolhapur": "MH09", "Solapur": "MH13", "Aurangabad": "MH20", "Bhiwandi": "MH04", "Panvel": "MH46", "Surat": "GJ05", "Ahmedabad": "GJ01",
       "New Delhi": "DL3C", "Hyderabad": "TS09", "Bengaluru": "KA01", "Kolkata": "WB02", "Jaipur": "RJ14", "Lucknow": "UP32", "Indore": "MP09",
       "Panaji": "GA07", "Chennai": "TN01", "Kochi": "KL07"}

# GST state codes
GST_STATE = {"MH": "27", "GJ": "24", "DL": "07", "TS": "36", "KA": "29", "WB": "19", "RJ": "08", "UP": "09", "MP": "23", "GA": "30", "TN": "33", "KL": "32"}

# highways between the cities, for toll plazas and journeys
ROUTES: list[tuple[str, str, str]] = [
    ("Mumbai", "Pune", "Mumbai-Pune Expressway"), ("Mumbai", "Nashik", "NH160"), ("Mumbai", "Surat", "NH48"), ("Surat", "Ahmedabad", "NH48"),
    ("Pune", "Kolhapur", "NH48"), ("Pune", "Solapur", "NH65"), ("Pune", "Aurangabad", "NH753F"), ("Nashik", "Aurangabad", "NH752G"),
    ("Aurangabad", "Nagpur", "Samruddhi Mahamarg"), ("Nagpur", "Hyderabad", "NH44"), ("Hyderabad", "Bengaluru", "NH44"),
    ("Bengaluru", "Chennai", "NH48"), ("Solapur", "Hyderabad", "NH65"), ("Kolhapur", "Panaji", "NH748"), ("Ahmedabad", "Jaipur", "NH48"),
    ("Jaipur", "New Delhi", "NH48"), ("New Delhi", "Lucknow", "Agra-Lucknow Expressway"), ("Indore", "Nagpur", "NH47"),
    ("Indore", "Ahmedabad", "NH47"), ("Kochi", "Bengaluru", "NH544"), ("Mumbai", "Panaji", "NH66"), ("Chennai", "Kochi", "NH544"),
]
# satellite towns travel through their metropolis
HUB = {"Andheri": "Mumbai", "Thane": "Mumbai", "Navi Mumbai": "Mumbai", "Bhiwandi": "Mumbai", "Panvel": "Mumbai"}
