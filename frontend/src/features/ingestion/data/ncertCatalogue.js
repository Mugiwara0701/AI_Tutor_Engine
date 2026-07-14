// src/features/ingestion/data/ncertCatalogue.js
//
// Local NCERT book catalogue used to power the dependent
// Board -> Class -> Subject -> Book dropdowns in the Upload New Book modal.
// This is frontend-only mock data — nothing here is fetched from a server.
//
// Shape:
// {
//   [board]: {
//     [className]: {
//       [subject]: [ "Book Name", ... ]
//     }
//   }
// }

const NCERT_CLASS_CATALOGUE = {
  "Class 1": {
    Hindi: ["Rimjhim"],
    English: ["Marigold"],
    Mathematics: ["Math Magic"],
  },
  "Class 2": {
    Hindi: ["Rimjhim"],
    English: ["Marigold"],
    Mathematics: ["Math Magic"],
  },
  "Class 3": {
    Hindi: ["Rimjhim"],
    English: ["Marigold"],
    Mathematics: ["Math Magic"],
    "Environmental Studies": ["Looking Around"],
  },
  "Class 4": {
    Hindi: ["Rimjhim"],
    English: ["Marigold"],
    Mathematics: ["Math Magic"],
    "Environmental Studies": ["Looking Around"],
  },
  "Class 5": {
    Hindi: ["Rimjhim"],
    English: ["Marigold"],
    Mathematics: ["Math Magic"],
    "Environmental Studies": ["Looking Around"],
  },
  "Class 6": {
    Hindi: ["Vasant Part 1", "Bal Ram Katha", "Durva Part 1"],
    English: ["Honeysuckle", "A Pact With The Sun (Supplementary)"],
    Mathematics: ["Mathematics"],
    Science: ["Science"],
    "Social Science": [
      "History – Our Pasts Part 1",
      "Geography – The Earth Our Habitat Part 1",
      "Civics – Social and Political Life Part 1",
    ],
    Sanskrit: ["Ruchira Part 1"],
  },
  "Class 7": {
    Hindi: ["Vasant Part 2", "Mahabharat", "Durva Part 2"],
    English: ["Honeycomb", "An Alien Hand (Supplementary)"],
    Mathematics: ["Mathematics"],
    Science: ["Science"],
    "Social Science": [
      "History – Our Pasts Part 2",
      "Geography – Our Environment Part 2",
      "Civics – Social and Political Life Part 2",
    ],
    Sanskrit: ["Ruchira Part 2"],
  },
  "Class 8": {
    Hindi: ["Vasant Part 3", "Bharat Ki Khoj", "Durva Part 3"],
    English: ["Honeydew", "It So Happened (Supplementary)"],
    Mathematics: ["Mathematics"],
    Science: ["Science"],
    "Social Science": [
      "History – Our Pasts Part 3",
      "Geography – Resources and Development Part 3",
      "Civics – Social and Political Life Part 3",
    ],
    Sanskrit: ["Ruchira Part 3"],
  },
  "Class 9": {
    "Hindi Course A": ["Kshitij Part 1", "Kritika Part 1"],
    "Hindi Course B": ["Sparsh Part 1", "Sanchayan Part 1"],
    English: ["Beehive", "Moments (Supplementary)"],
    Mathematics: ["Mathematics"],
    Science: ["Science"],
    "Social Science": [
      "History – India and the Contemporary World Part 1",
      "Geography – Contemporary India Part 1",
      "Political Science – Democratic Politics Part 1",
      "Economics",
    ],
    Sanskrit: ["Shemushi Part 1"],
  },
  "Class 10": {
    "Hindi Course A": ["Kshitij Part 2", "Kritika Part 2"],
    "Hindi Course B": ["Sparsh Part 2", "Sanchayan Part 2"],
    English: ["First Flight", "Footprints Without Feet (Supplementary)"],
    Mathematics: ["Mathematics"],
    Science: ["Science"],
    "Social Science": [
      "History – India and the Contemporary World Part 2",
      "Geography – Contemporary India Part 2",
      "Political Science – Democratic Politics Part 2",
      "Economics – Understanding Economic Development",
    ],
    Sanskrit: ["Shemushi Part 2"],
  },
  "Class 11": {
    Physics: ["Physics Part 1", "Physics Part 2", "Physics Lab Manual"],
    Chemistry: ["Chemistry Part 1", "Chemistry Part 2", "Chemistry Lab Manual"],
    Mathematics: ["Mathematics"],
    Biology: ["Biology", "Biology Lab Manual"],
    English: ["Hornbill", "Snapshots (Supplementary)"],
    "Hindi Core": ["Aroh Part 1", "Vitan Part 1"],
    "Hindi Elective": ["Antra Part 1", "Antral Part 1"],
    Accountancy: ["Financial Accounting Part 1", "Financial Accounting Part 2"],
    "Business Studies": ["Business Studies Part 1"],
    Economics: ["Indian Economic Development", "Statistics for Economics"],
    History: ["Themes in World History"],
    Geography: [
      "Fundamentals of Physical Geography",
      "India – Physical Environment",
      "Practical Work in Geography Part 1",
    ],
    "Political Science": [
      "Political Theory",
      "Indian Constitution at Work",
    ],
    Psychology: ["Introduction to Psychology"],
    Sociology: ["Introducing Sociology", "Understanding Society"],
    "Computer Science": ["Computer Science"],
    "Informatics Practices": ["Informatics Practices"],
    "Physical Education": ["Physical Education"],
    "Home Science": ["Human Ecology and Family Sciences Part 1"],
  },
  "Class 12": {
    Physics: ["Physics Part 1", "Physics Part 2", "Physics Lab Manual"],
    Chemistry: ["Chemistry Part 1", "Chemistry Part 2", "Chemistry Lab Manual"],
    Mathematics: ["Mathematics Part 1", "Mathematics Part 2"],
    Biology: ["Biology", "Biology Lab Manual"],
    English: ["Flamingo", "Vistas (Supplementary)"],
    "Hindi Core": ["Aroh Part 2", "Vitan Part 2"],
    "Hindi Elective": ["Antra Part 2", "Antral Part 2"],
    Accountancy: [
      "Accountancy Part 1",
      "Accountancy Part 2",
      "Company Accounts and Analysis of Financial Statements",
    ],
    "Business Studies": ["Business Studies Part 1", "Business Studies Part 2"],
    Economics: ["Macroeconomics", "Indian Economic Development"],
    History: [
      "Themes in Indian History Part 1",
      "Themes in Indian History Part 2",
      "Themes in Indian History Part 3",
    ],
    Geography: [
      "Fundamentals of Human Geography",
      "India – People and Economy",
      "Practical Work in Geography Part 2",
    ],
    "Political Science": [
      "Contemporary World Politics",
      "Politics in India Since Independence",
    ],
    Psychology: ["Psychology"],
    Sociology: ["Indian Society", "Social Change and Development in India"],
    "Computer Science": ["Computer Science"],
    "Informatics Practices": ["Informatics Practices"],
    "Physical Education": ["Physical Education"],
    "Home Science": ["Human Ecology and Family Sciences Part 2"],
    "Entrepreneurship": ["Entrepreneurship"],
  },
};

// The catalogue is keyed by board for future flexibility. All boards
// currently point at the same NCERT-aligned class catalogue for this
// frontend-only demo.
export const NCERT_CATALOGUE = {
  CBSE: NCERT_CLASS_CATALOGUE,
  ICSE: NCERT_CLASS_CATALOGUE,
  "State Board": NCERT_CLASS_CATALOGUE,
};

export const BOARD_OPTIONS = Object.keys(NCERT_CATALOGUE);

export function getClassOptions(board) {
  if (!board || !NCERT_CATALOGUE[board]) return [];
  return Object.keys(NCERT_CATALOGUE[board]);
}

export function getSubjectOptions(board, className) {
  if (!board || !className) return [];
  return Object.keys(NCERT_CATALOGUE[board]?.[className] ?? {});
}

export function getBookOptions(board, className, subject) {
  if (!board || !className || !subject) return [];
  return NCERT_CATALOGUE[board]?.[className]?.[subject] ?? [];
}

export const CURRICULUM_YEAR_OPTIONS = ["2026", "2025", "2024"];
