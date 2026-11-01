"""Name bank for synthetic Indian persons: (Latin, Devanagari) pairs.

Weighted toward Maharashtra (the pilot state) with Muslim and North Indian names that are
common in Maharashtra's cities. Romanisations are the most frequent official spellings.
"""

MARATHI_MALE = [
    ("Ramesh", "रमेश"), ("Suresh", "सुरेश"), ("Mahesh", "महेश"), ("Ganesh", "गणेश"), ("Santosh", "संतोष"),
    ("Prakash", "प्रकाश"), ("Vijay", "विजय"), ("Sanjay", "संजय"), ("Ajay", "अजय"), ("Anil", "अनिल"),
    ("Sunil", "सुनील"), ("Rahul", "राहुल"), ("Amol", "अमोल"), ("Sachin", "सचिन"), ("Nitin", "नितीन"),
    ("Vishal", "विशाल"), ("Sagar", "सागर"), ("Rohit", "रोहित"), ("Akash", "आकाश"), ("Dattatray", "दत्तात्रय"),
    ("Vishnu", "विष्णू"), ("Balasaheb", "बाळासाहेब"), ("Dnyaneshwar", "ज्ञानेश्वर"), ("Tukaram", "तुकाराम"),
    ("Shivaji", "शिवाजी"), ("Pandurang", "पांडुरंग"), ("Mangesh", "मंगेश"), ("Yogesh", "योगेश"), ("Kiran", "किरण"),
    ("Swapnil", "स्वप्नील"), ("Pravin", "प्रवीण"), ("Dilip", "दिलीप"), ("Vikas", "विकास"), ("Raju", "राजू"),
    ("Vishwas", "विश्वास"), ("Bhushan", "भूषण"), ("Tushar", "तुषार"), ("Nilesh", "निलेश"),
]
MARATHI_FEMALE = [
    ("Sunita", "सुनीता"), ("Anita", "अनिता"), ("Kavita", "कविता"), ("Savita", "सविता"), ("Manisha", "मनीषा"),
    ("Priya", "प्रिया"), ("Pooja", "पूजा"), ("Snehal", "स्नेहल"), ("Ashwini", "अश्विनी"), ("Rupali", "रुपाली"),
    ("Jyoti", "ज्योती"), ("Vaishali", "वैशाली"), ("Shobha", "शोभा"), ("Lata", "लता"), ("Sangita", "संगीता"),
    ("Swati", "स्वाती"), ("Madhuri", "माधुरी"), ("Sarika", "सारिका"),
]
MARATHI_SURNAMES = [
    ("Patil", "पाटील"), ("Pawar", "पवार"), ("Jadhav", "जाधव"), ("Shinde", "शिंदे"), ("Deshmukh", "देशमुख"),
    ("Kulkarni", "कुलकर्णी"), ("Joshi", "जोशी"), ("More", "मोरे"), ("Gaikwad", "गायकवाड"), ("Chavan", "चव्हाण"),
    ("Kale", "काळे"), ("Bhosale", "भोसले"), ("Salunkhe", "साळुंखे"), ("Kadam", "कदम"), ("Mane", "माने"),
    ("Shelke", "शेळके"), ("Wagh", "वाघ"), ("Thorat", "थोरात"), ("Kamble", "कांबळे"), ("Sawant", "सावंत"),
    ("Deshpande", "देशपांडे"), ("Raut", "राऊत"), ("Nikam", "निकम"), ("Mhatre", "म्हात्रे"), ("Bhagat", "भगत"),
    ("Lokhande", "लोखंडे"), ("Waghmare", "वाघमारे"), ("Sonawane", "सोनवणे"), ("Kharat", "खरात"), ("Gawade", "गावडे"),
]
MUSLIM_MALE = [
    ("Irfan", "इरफान"), ("Salim", "सलीम"), ("Imran", "इमरान"), ("Javed", "जावेद"), ("Aslam", "असलम"),
    ("Rafiq", "रफीक"), ("Sajid", "साजिद"), ("Arif", "आरिफ"), ("Faisal", "फैसल"), ("Sameer", "समीर"),
    ("Yusuf", "यूसुफ"), ("Abdul", "अब्दुल"), ("Mohammed", "मोहम्मद"), ("Shahid", "शाहिद"),
]
MUSLIM_FEMALE = [("Ayesha", "आयशा"), ("Shabana", "शबाना"), ("Rukhsar", "रुखसार"), ("Nazia", "नाझिया"), ("Farhana", "फरहाना")]
MUSLIM_SURNAMES = [
    ("Shaikh", "शेख"), ("Khan", "खान"), ("Sayyed", "सय्यद"), ("Pathan", "पठाण"), ("Ansari", "अन्सारी"),
    ("Qureshi", "कुरेशी"), ("Inamdar", "इनामदार"), ("Mulla", "मुल्ला"), ("Tamboli", "तांबोळी"), ("Attar", "अत्तार"),
]
NORTH_MALE = [
    ("Rajesh", "राजेश"), ("Amit", "अमित"), ("Manoj", "मनोज"), ("Pankaj", "पंकज"), ("Deepak", "दीपक"),
    ("Ravi", "रवी"), ("Ashok", "अशोक"), ("Ramesh", "रमेश"),
]
NORTH_FEMALE = [("Neha", "नेहा"), ("Rekha", "रेखा"), ("Seema", "सीमा"), ("Anjali", "अंजली")]
NORTH_SURNAMES = [
    ("Sharma", "शर्मा"), ("Yadav", "यादव"), ("Singh", "सिंह"), ("Gupta", "गुप्ता"), ("Mishra", "मिश्रा"),
    ("Verma", "वर्मा"), ("Tiwari", "तिवारी"), ("Chauhan", "चौहान"), ("Pandey", "पांडे"),
]

COMMUNITIES = [
    # weight, male, female, surnames
    (0.68, MARATHI_MALE, MARATHI_FEMALE, MARATHI_SURNAMES),
    (0.20, MUSLIM_MALE, MUSLIM_FEMALE, MUSLIM_SURNAMES),
    (0.12, NORTH_MALE, NORTH_FEMALE, NORTH_SURNAMES),
]

# Canary identities: deliberately rare, never used by the generator for anyone else.
CANARIES = [
    ("Kaustubh Narhar Jog", "कौस्तुभ नरहर जोग", "M"),
    ("Tejaswini Damodar Ghaisas", "तेजस्विनी दामोदर घैसास", "F"),
]

# Clerk-style romanisation noise: (pattern, replacement)
SPELLING_NOISE = [
    ("sh", "s"), ("v", "w"), ("w", "v"), ("ee", "i"), ("i", "ee"), ("oo", "u"), ("u", "oo"),
    ("aa", "a"), ("a", "aa"), ("dh", "d"), ("th", "t"), ("kh", "k"), ("bh", "b"), ("ph", "f"),
    ("ksh", "x"), ("j", "z"), ("y", "i"), ("e", "a"),
]
